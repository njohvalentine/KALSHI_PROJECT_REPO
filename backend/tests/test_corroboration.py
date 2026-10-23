"""Corroboration, phase 1 (FEAT-20261023-1131): the registered domain, which pages are asked about which claims, the arithmetic of the report and that nothing is written. Fake judge, no network."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import load_settings
from app.models import ClaimCheck, Run, SourcePage
from app.research.check import ClaimVerdict
from app.research.corroboration import corroborate_run, format_report, pick_runs, summarise
from app.research.schemas import Usage
from app.research.source_trust import registered_domain
from tests.conftest import alembic_config, needs_db

SETTINGS = load_settings({"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40, "OPENAI_API_KEY": "sk-test"})
NOW = datetime.now(UTC)


@pytest.mark.parametrize("host,domain", [
    ("www.bbc.co.uk", "bbc.co.uk"), ("de.uefa.com", "uefa.com"), ("images.mlssoccer.com", "mlssoccer.com"), ("a.b.com.au", "b.com.au"), ("uefa.com", "uefa.com"),
    ("sub.club.example.org", "example.org"), ("npb.jp", "npb.jp"), ("news.test", "news.test"), ("localhost", "localhost"), ("", ""), ("kicker.de", "kicker.de"),
])
def test_the_registered_domain(host, domain):
    assert registered_domain(host) == domain


TEXT_A = "Newcastle beat Arsenal 2-1 on Saturday 10 October 2026 at St James' Park. " * 6
TEXT_B = "Newcastle beat Arsenal 2-1 in the league on 10 October 2026, said the report. " * 6
TEXT_C = "Nothing about that match here, only a table of other results. " * 8
FINDINGS = [{"angle": "Form", "kind": "evidence", "question": "q", "claims": [
    {"text": "Newcastle beat Arsenal 2-1", "kind": "sourced", "sources": [{"url": "https://www.uefa.com/a", "title": "t"}]},
    {"text": "Arsenal drew twice", "kind": "sourced", "sources": [{"url": "https://www.uefa.com/a", "title": "t"}]}]}]


class FakeJudge:
    """Says "supported" for the claim numbers listed per page url; remembers what it was asked."""

    def __init__(self, supported=None):
        self.supported, self.calls = supported or {}, []

    async def judge(self, game_title, page_url, page_title, page_text, cut, claims):
        self.calls.append({"url": page_url, "claims": list(claims)})
        out = []
        for n, claim in enumerate(claims, 1):
            if (page_url, claim) in self.supported:
                out.append(ClaimVerdict(claim_number=n, verdict="supported", quotes=[self.supported[(page_url, claim)]], reason="the page says it"))
            else:
                out.append(ClaimVerdict(claim_number=n, verdict="could_not_check", quotes=[], reason="not on the page"))
        return out, Usage("gpt-5.4-mini", 3000, 0, 100)


def page(run, url, text, final=None, status="ok"):
    return SourcePage(run_id=run, url=url, final_url=final, title="T", retrieved_at=NOW, fetch_status=status, content_hash=url, content=text, page_text=text, page_text_hash=url)


def setup(fresh_db, run_id="r1"):
    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        db.add(Run(id=run_id, event_ticker="KXUCLGAME-26OCT12NEWARS", event_title="Newcastle vs Arsenal", status="done", result={"findings": FINDINGS}))
        db.flush()
        db.add_all([page(run_id, "https://www.uefa.com/a", TEXT_A), page(run_id, "https://de.uefa.com/b", TEXT_A), page(run_id, "https://www.bbc.co.uk/c", TEXT_B),
                    page(run_id, "https://other.example/d", TEXT_C), page(run_id, "https://down.example/e", TEXT_B, status="failed")])
        db.add(ClaimCheck(run_id=run_id, finding_index=0, claim_index=0, source_url="https://www.uefa.com/a", verdict="supported", reason="ok", model="m"))
        db.add(ClaimCheck(run_id=run_id, finding_index=0, claim_index=1, source_url="https://www.uefa.com/a", verdict="supported", reason="ok", model="m"))
        db.commit()


@needs_db
def test_only_pages_of_other_domains_are_asked_and_a_second_domain_counts_once(fresh_db):
    setup(fresh_db)
    judge = FakeJudge({("https://www.bbc.co.uk/c", "Newcastle beat Arsenal 2-1"): "Newcastle beat Arsenal 2-1 in the league on 10 October 2026"})
    results, usages = asyncio.run(corroborate_run(fresh_db, "r1", judge, SETTINGS))
    asked = {c["url"]: c["claims"] for c in judge.calls}
    assert "https://de.uefa.com/b" not in asked and "https://www.uefa.com/a" not in asked  # same registered domain as the page that already supports both claims
    assert "https://down.example/e" not in asked  # a page that could not be read is never asked
    assert set(asked) == {"https://www.bbc.co.uk/c", "https://other.example/d"} and asked["https://www.bbc.co.uk/c"] == ["Newcastle beat Arsenal 2-1", "Arsenal drew twice"]
    by_claim = {r["claim_index"]: r for r in results}
    assert by_claim[0]["domains"] == ["bbc.co.uk", "uefa.com"] and by_claim[1]["domains"] == ["uefa.com"]
    assert by_claim[0]["extra"][0]["quote"].startswith("Newcastle beat Arsenal 2-1") and by_claim[0]["sport"] == "Soccer"
    assert len(usages) == 2


@needs_db
def test_a_quote_that_is_not_on_the_page_does_not_corroborate(fresh_db):
    setup(fresh_db)
    judge = FakeJudge({("https://www.bbc.co.uk/c", "Newcastle beat Arsenal 2-1"): "a sentence that is not on that page at all"})
    results, _ = asyncio.run(corroborate_run(fresh_db, "r1", judge, SETTINGS))
    assert [r["domains"] for r in sorted(results, key=lambda r: r["claim_index"])] == [["uefa.com"], ["uefa.com"]]  # the app's own quote check applies


@needs_db
def test_the_domain_of_the_page_really_reached_is_used_and_nothing_is_written(fresh_db):
    setup(fresh_db)
    with DbSession(fresh_db) as db:
        # a redirect: the cited bbc.co.uk page really was on uefa.com
        row = db.scalars(select(SourcePage).where(SourcePage.url == "https://www.bbc.co.uk/c")).one()
        row.final_url = "https://www.uefa.com/moved"
        db.commit()
        before = (db.scalar(select(func.count()).select_from(ClaimCheck)), db.scalar(select(func.count()).select_from(SourcePage)), db.scalar(select(func.count()).select_from(Run)))
    judge = FakeJudge({("https://www.bbc.co.uk/c", "Newcastle beat Arsenal 2-1"): "Newcastle beat Arsenal 2-1 in the league on 10 October 2026"})
    results, _ = asyncio.run(corroborate_run(fresh_db, "r1", judge, SETTINGS))
    assert "https://www.bbc.co.uk/c" not in {c["url"] for c in judge.calls}  # same domain as the support after the redirect
    assert all(r["domains"] == ["uefa.com"] for r in results)
    with DbSession(fresh_db) as db:
        assert before == (db.scalar(select(func.count()).select_from(ClaimCheck)), db.scalar(select(func.count()).select_from(SourcePage)), db.scalar(select(func.count()).select_from(Run)))


@needs_db
def test_the_runs_are_picked_by_seed_and_only_runs_with_supported_claims(fresh_db):
    setup(fresh_db, "r1")
    with DbSession(fresh_db) as db:
        db.add(Run(id="r2", event_ticker="K2", event_title="A vs B", status="done", result={"findings": FINDINGS}))  # no supported claim
        db.commit()
    assert pick_runs(fresh_db, 5, 1) == ["r1"] and pick_runs(fresh_db, 5, 1) == pick_runs(fresh_db, 5, 2)


def result(run, ci, sport, domains, quote=""):
    return {"run_id": run, "finding_index": 0, "claim_index": ci, "text": f"claim {ci}", "sport": sport, "domains": domains, "support_domains": domains[:1],
            "extra": [{"domain": d, "url": f"https://{d}/x", "quote": quote or "q", "reason": "r"} for d in domains[1:]]}


def test_the_report_arithmetic_and_the_rule_for_the_next_step():
    rows = [result("a", 0, "Soccer", ["uefa.com", "bbc.co.uk"]), result("a", 1, "Soccer", ["uefa.com"]), result("b", 0, "Tennis", ["atptour.com"]),
            result("b", 1, "Tennis", ["atptour.com", "x.com", "y.com"])]
    s = summarise(rows, [Usage("gpt-5.4-mini", 1_000_000, 0, 0)], runs=2)
    assert s["claims"] == 4 and s["corroborated"] == 2 and s["share"] == 0.5 and s["by_sport"] == {"Soccer": (1, 2), "Tennis": (1, 2)} and s["distribution"] == {1: 2, 2: 1, 3: 1}
    assert s["cost_usd"] == pytest.approx(0.75)
    text = format_report(s, rows, sample=2, seed=1)
    assert "50%" in text and "Soccer" in text and "25 percent" in text and "hand check" in text.lower()
