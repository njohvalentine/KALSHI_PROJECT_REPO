"""Scores the claim checker against the hand-labelled sample in tests/data/claim_labels.json.

Run (spends a few cents of OpenAI credit; needs OPENAI_API_KEY and the required settings in the environment):
    cd backend && set -a && source ../.env && set +a && uv run python -m app.research.score_checker

Each case is one claim and one page, judged exactly as in a real run (same prompt, same page cut,
same quote checks). Cases marked "borderline" are ones where a careful person could label either
way; they are reported separately and do not count towards accuracy. The labels were written by the
assistant that built the checker and need a spot-check by a person (see the spec, task 4)."""

import asyncio
import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from app.config import load_settings
from app.research.check import ClaimJudge, OpenAIClaimJudge, decide, unreadable_reason
from app.research.pricing import cost_usd
from app.research.prompts import PAGE_TAG
from app.research.schemas import Usage

SAMPLE = Path(__file__).resolve().parents[2] / "tests" / "data" / "claim_labels.json"
LABELS = ("supported", "not_supported", "could_not_check")


async def judge_case(case: dict, judge: ClaimJudge, page_chars: int) -> dict:
    """What the checker would save for this case: the final verdict, the judge's own verdict, the reason, the usage."""
    why = unreadable_reason(case["page_status"], None, case["page_text"])
    if why:
        return {"got": "could_not_check", "judge": "(no call)", "reason": why, "usage": None}
    text = case["page_text"]
    shown = PAGE_TAG.sub("[tag removed]", text[:page_chars])
    verdicts, usage = await judge.judge(case["game"], case["url"], None, shown, len(text) > page_chars, [case["claim"]])
    answer = verdicts[0] if len(verdicts) == 1 and verdicts[0].claim_number == 1 else None
    got, reason = decide(answer, shown, case["claim"])
    return {"got": got, "judge": answer.verdict if answer else "(no answer)", "reason": reason, "usage": usage,
            "quote": answer.quote if answer else ""}


def score(cases: list[dict], results: list[dict]) -> dict:
    """Counts. `false_supported` (checker says supported, label says otherwise) is the number that must stay at zero."""
    firm = [(c, r) for c, r in zip(cases, results) if not c["borderline"]]
    border = [(c, r) for c, r in zip(cases, results) if c["borderline"]]
    return {
        "cases": len(cases), "firm": len(firm), "borderline": len(border),
        "firm_correct": sum(r["got"] == c["label"] for c, r in firm),
        "borderline_agree": sum(r["got"] == c["label"] for c, r in border),
        "false_supported": [c["id"] for c, r in zip(cases, results) if r["got"] == "supported" and c["label"] != "supported"],
        "missed_supported": [c["id"] for c, r in zip(cases, results) if c["label"] == "supported" and r["got"] != "supported"],
        "downgraded_by_quote_check": [c["id"] for c, r in zip(cases, results)
                                      if r["judge"] in ("supported", "not_supported") and r["got"] == "could_not_check"],
        "confusion": {f"{k[0]} -> {k[1]}": n for k, n in Counter((c["label"], r["got"]) for c, r in firm).items()},
    }


async def run(path: Path = SAMPLE) -> None:
    settings = load_settings(os.environ)
    if not settings.openai_api_key:
        sys.exit("OPENAI_API_KEY is not set: the real judge cannot run.")
    cases = json.loads(path.read_text())
    judge = OpenAIClaimJudge(settings)
    results = await asyncio.gather(*(judge_case(c, judge, settings.check_page_chars) for c in cases))
    usages = [r["usage"] for r in results if r["usage"]]
    cost = sum((cost_usd(u) or Decimal(0) for u in usages), Decimal(0))
    for c, r in zip(cases, results):
        mark = "ok " if r["got"] == c["label"] else "MISS"
        print(f'{mark} {c["id"]:26} label={c["label"]:16} got={r["got"]:16} judge={r["judge"]:16}'
              f'{" borderline" if c["borderline"] else ""}{" synthetic" if c["synthetic"] else ""}')
        if r["got"] != c["label"] or r["judge"] != r["got"]:
            print(f'     {r["reason"][:230]}')
            if "not found" in r["reason"]:
                print(f'     judge quote: {r.get("quote", "")[:300]!r}')
    summary = score(cases, results)
    print(json.dumps(summary, indent=1))
    print(f"Judge calls: {len(usages)}, input tokens {sum(u.input_tokens for u in usages)}, "
          f"output tokens {sum(u.output_tokens for u in usages)}, cost {cost} USD")


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE))
