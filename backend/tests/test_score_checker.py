"""The labelled sample is well formed, and the scoring code counts what it says. No network, no key."""

import asyncio
import json

import pytest

from app.research.check import ClaimVerdict
from app.research.schemas import Usage
from app.research.score_checker import LABELS, SAMPLE, judge_case, score

CASES = json.loads(SAMPLE.read_text())


def test_sample_is_well_formed_and_covers_every_kind_of_case():
    assert len(CASES) >= 20 and len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert c["label"] in LABELS and c["claim"].strip() and c["note"].strip()
        assert isinstance(c["borderline"], bool) and isinstance(c["synthetic"], bool)
        assert c["page_status"] == "ok" or c["page_text"] is None
        assert len(c["page_text"] or "") <= 5000  # short excerpts only
    labels = {c["label"] for c in CASES}
    assert labels == set(LABELS)
    assert any(c["page_status"] != "ok" for c in CASES) and any(c["synthetic"] for c in CASES)
    assert sum(c["borderline"] for c in CASES) < len(CASES) / 2  # most labels are firm


class OneVerdictJudge:
    def __init__(self, verdict):
        self.verdict = verdict

    async def judge(self, game, url, title, text, cut, claims):
        return [self.verdict], Usage("gpt-5.4-mini", 1000, 0, 50)


def case(**kw):
    base = dict(id="x", game="g", claim="Team A won 2-1", url="https://a.test", page_status="ok", page_text="Team A won 2-1 on Saturday. " * 20,
                label="supported", borderline=False, synthetic=False, note="n")
    return base | kw


def test_judge_case_applies_the_same_checks_as_a_run():
    good = ClaimVerdict(claim_number=1, verdict="supported", quotes=["Team A won 2-1 on Saturday"], reason="stated")
    assert asyncio.run(judge_case(case(), OneVerdictJudge(good), 30000))["got"] == "supported"
    invented = ClaimVerdict(claim_number=1, verdict="supported", quotes=["Team A won 5-0 at Wembley Stadium"], reason="x")
    out = asyncio.run(judge_case(case(), OneVerdictJudge(invented), 30000))
    assert out["got"] == "could_not_check" and out["judge"] == "supported"
    unreadable = asyncio.run(judge_case(case(page_status="failed", page_text=None), OneVerdictJudge(good), 30000))
    assert unreadable["judge"] == "(no call)" and unreadable["usage"] is None


def test_score_counts_false_supported_missed_supported_and_borderline_separately():
    cases = [case(id="a"), case(id="b", label="not_supported"), case(id="c"), case(id="d", label="could_not_check", borderline=True),
             case(id="e", label="supported", borderline=True)]
    got = ["supported", "supported", "could_not_check", "could_not_check", "supported"]
    judge = ["supported", "supported", "supported", "could_not_check", "supported"]
    results = [{"got": g, "judge": j} for g, j in zip(got, judge)]
    s = score(cases, results)
    assert (s["cases"], s["firm"], s["borderline"]) == (5, 3, 2)
    assert s["firm_correct"] == 1 and s["borderline_agree"] == 2
    assert s["false_supported"] == ["b"] and s["missed_supported"] == ["c"] and s["downgraded_by_quote_check"] == ["c"]
