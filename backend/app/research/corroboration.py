"""Corroboration, phase 1 (FEAT-20261023-1131): how many of the facts a run found could be supported by a SECOND independent website, among the pages that run already read.

Read-only. For each supported claim the judge (the app's own, with its own quote and number check) is asked about the saved pages of the same run that are from a
registered domain other than the pages that already support the claim; nothing is saved. "Independent" means a different registered domain, judged on the address
the fetcher really reached; two sites that print the same wire story look independent here, which cannot be detected (a stated limit)."""

import asyncio
import random
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import ClaimCheck, OutcomeRecord, Run, SourcePage
from app.research.check import ClaimJudge, decide, supported_claims
from app.research.pricing import cost_usd
from app.research.prompts import remove_page_tags
from app.research.schemas import Usage
from app.research.source_trust import host_of, registered_domain

RULE_SHARE = 0.25  # phase 2 is only worth proposing if at least this share of supported claims get a second independent domain ...
RULE_HAND = (17, 20)  # ... and the hand check finds the second page really states the same fact in at least 17 of 20 cases


def _domain(url: str, final: str | None) -> str:
    return registered_domain(host_of(final or url))


def pick_runs(engine, n: int, seed: int) -> list[str]:
    """`n` saved runs that have at least one supported claim, chosen by a seeded shuffle (the same seed gives the same runs)."""
    with DbSession(engine) as db:
        ids = sorted(db.scalars(select(ClaimCheck.run_id).where(ClaimCheck.verdict == "supported").distinct()).all())
    random.Random(seed).shuffle(ids)
    return ids[:n]


def _sport(db, run: Run, settings: Settings) -> str:
    sport = db.scalar(select(OutcomeRecord.sport).where(OutcomeRecord.run_id == run.id, OutcomeRecord.sport.is_not(None)).limit(1))
    if sport:
        return sport
    series = run.event_ticker.split("-")[0]
    return next((e.sport for e in settings.sports_series if e.ticker == series), "unknown")


async def corroborate_run(engine, run_id: str, judge: ClaimJudge, settings: Settings) -> tuple[list[dict], list[Usage]]:
    with DbSession(engine) as db:
        run = db.get(Run, run_id)
        if run is None or not run.result:
            raise ValueError(f"Run {run_id} has no result")
        findings, title, sport = run.result["findings"], run.event_title, _sport(db, run, settings)
        checks = db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == run_id)).all()
        pages = [(p.url, p.final_url, p.title, p.page_text) for p in db.scalars(select(SourcePage).where(SourcePage.run_id == run_id).order_by(SourcePage.id)) if p.fetch_status == "ok" and p.page_text]
    finals = {url: final for url, final, _, _ in pages if final}
    claims = supported_claims(findings, checks, finals)
    for c in claims:
        c["support_domains"] = sorted({_domain(u, finals.get(u)) for u in c["supported_by"]})
        c["extra"] = []
    usages: list[Usage] = []
    semaphore = asyncio.Semaphore(settings.check_concurrency)

    async def one_page(url: str, final: str | None, page_title: str | None, text: str) -> None:
        domain = _domain(url, final)
        todo = [c for c in claims if domain not in c["support_domains"]]
        if not todo:
            return
        shown = remove_page_tags(text[: settings.check_page_chars])  # exactly what the judge is shown, as in the normal check
        async with semaphore:
            verdicts, usage = await judge.judge(title, url, page_title, shown, len(text) > settings.check_page_chars, [c["text"] for c in todo])
        usages.append(usage)
        by_number = {v.claim_number: v for v in verdicts}
        for n, c in enumerate(todo, 1):
            v = by_number.get(n)
            if decide(v, shown, c["text"])[0] == "supported":
                c["extra"].append({"domain": domain, "url": url, "quote": (v.quotes or [""])[0], "reason": v.reason})

    await asyncio.gather(*(one_page(*p) for p in pages))
    out = []
    for c in claims:
        extra = sorted(c["extra"], key=lambda e: e["domain"])
        seen: dict[str, dict] = {}
        for e in extra:  # one entry per domain
            seen.setdefault(e["domain"], e)
        out.append({"run_id": run_id, "finding_index": c["finding_index"], "claim_index": c["claim_index"], "text": c["text"], "sport": sport,
                    "support_domains": c["support_domains"], "domains": sorted(set(c["support_domains"]) | set(seen)), "extra": list(seen.values())})
    return out, usages


def summarise(rows: list[dict], usages: list[Usage], runs: int) -> dict:
    corroborated = sum(1 for r in rows if len(r["domains"]) >= 2)
    by_sport: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        by_sport[r["sport"]][1] += 1
        by_sport[r["sport"]][0] += len(r["domains"]) >= 2
    costs = [cost_usd(u) for u in usages]
    return {"runs": runs, "claims": len(rows), "corroborated": corroborated, "share": corroborated / len(rows) if rows else 0.0,
            "by_sport": {k: (v[0], v[1]) for k, v in sorted(by_sport.items())}, "distribution": dict(sorted(Counter(len(r["domains"]) for r in rows).items())),
            "judge_calls": len(usages), "cost_usd": float(sum(c for c in costs if c is not None)), "unpriced": any(c is None for c in costs)}


def format_report(s: dict, rows: list[dict], sample: int = 20, seed: int = 0) -> str:
    corroborated = [r for r in rows if len(r["domains"]) >= 2]
    picks = random.Random(seed).sample(corroborated, min(sample, len(corroborated)))
    lines = ["# Corroboration, phase 1: raw results", "",
             f"Runs: {s['runs']} saved runs with at least one supported claim. Supported claims: {s['claims']}. Judge calls: {s['judge_calls']}. Model cost: {s['cost_usd']:.2f} USD"
             + (" (some models unpriced)" if s["unpriced"] else "") + ".", "",
             f"**Claims that got a second independent website: {s['corroborated']} of {s['claims']} = {100 * s['share']:.0f}%.**", "",
             "| Sport | Corroborated | Claims | Share |", "|---|---|---|---|"]
    lines += [f"| {k} | {a} | {b} | {100 * a / b:.0f}% |" for k, (a, b) in s["by_sport"].items()]
    lines += ["", "Number of independent websites per claim: " + ", ".join(f"{k}: {v}" for k, v in s["distribution"].items()) + ".", "",
              f"## The rule for phase 2 (fixed before the run)", "",
              f"Phase 2 is proposed only if at least {int(RULE_SHARE * 100)} percent of the supported claims get a second independent website **and** the hand check below finds that the second page "
              f"states the same fact in at least {RULE_HAND[0]} of {RULE_HAND[1]} cases. Result of the first condition: {'met' if s['share'] >= RULE_SHARE else 'not met'}. The hand check follows.", "",
              f"## Hand check sample ({len(picks)} corroborated claims, seed {seed})", ""]
    for i, r in enumerate(picks, 1):
        e = r["extra"][0]
        lines += [f"{i}. **Claim:** {r['text']}  ", f"   Supported by: {', '.join(r['support_domains'])}  ", f"   Second site: {e['domain']} ({e['url']})  ", f"   Quote: “{e['quote']}”  ", f"   Judge: {e['reason']}", ""]
    return "\n".join(lines) + "\n"


async def run_test(engine, settings: Settings, judge: ClaimJudge, n: int, seed: int, log=lambda s: None) -> tuple[str, list[dict], dict]:
    runs = pick_runs(engine, n, seed)
    rows: list[dict] = []
    usages: list[Usage] = []
    for i, run_id in enumerate(runs, 1):
        got, used = await corroborate_run(engine, run_id, judge, settings)
        rows += got
        usages += used
        log(f"{i} of {len(runs)} runs done: {len(rows)} claims, {sum(1 for r in rows if len(r['domains']) >= 2)} corroborated")
    summary = summarise(rows, usages, len(runs))
    return format_report(summary, rows, 20, seed), rows, summary
