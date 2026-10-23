"""The lineup update's building blocks (FEAT-20261022-0956): the fixed angle per sport, the carry-over of earlier evidence, the graph without a planner, and the page rows that are not duplicated."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import load_settings
from app.models import ClaimCheck, Run, SourcePage
from app.research.graph import build_graph
from app.research.schemas import Angle
from app.research.sources import save_sources
from app.research.update import carry_over, update_angles
from tests.conftest import alembic_config, needs_db
from tests.fakes import FakeModel

SETTINGS = load_settings({"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40})
NOW = datetime.now(UTC)


@pytest.mark.parametrize("sport,name,words", [
    ("Soccer", "Lineups and late team news", ("starting lineup", "NOT", "published")), ("Baseball", "Probable pitchers and lineup cards", ("pitcher",)),
    ("Basketball", "Starters and injury report", ("starters", "injury")), ("Tennis", "Withdrawals and late match news", ("withdraw",)), (None, "Late team news", ("latest",)), ("Curling", "Late team news", ("latest",)),
])
def test_one_fixed_angle_per_sport_with_a_question_a_researcher_can_answer(sport, name, words):
    angles = update_angles(sport)
    assert len(angles) == 1 and angles[0].name == name and angles[0].kind == "evidence"
    assert all(w.lower() in angles[0].question.lower() for w in words)


def test_the_soccer_question_asks_for_who_is_missing_not_for_all_22_names():
    q = update_angles("Soccer")[0].question
    assert "regular starters" in q and "published" in q and "22" not in q  # the researcher writes at most 10 lines, one fact each


def test_the_graph_uses_fixed_angles_without_calling_the_planner():
    model = FakeModel(delay=0)
    graph = build_graph(model, SETTINGS)
    game = {"event_ticker": "KX-1", "title": "A vs B", "outcomes": ["A", "B"], "outcome_tickers": ["a", "b"], "exclusive": True}
    fixed = [Angle(name="Late team news", question="What is new?").model_dump()]
    state = asyncio.run(graph.ainvoke({"game": game, "fixed_angles": fixed}, {"configurable": {"thread_id": "t"}}))
    assert model.plan_calls == [] and model.research_calls == ["Late team news"] and state["usages"] and [a["name"] for a in state["angles"]] == ["Late team news"]
    plain = asyncio.run(build_graph(model, SETTINGS).ainvoke({"game": game}, {"configurable": {"thread_id": "t2"}}))
    assert len(model.plan_calls) == 1 and len(plain["angles"]) == 2  # without fixed angles the planner runs as before


FINDINGS = [
    {"angle": "Form", "question": "q1", "kind": "evidence", "claims": [{"text": "Home won 4 of 5", "kind": "sourced", "sources": [{"url": "https://form.test/a", "title": "A"}]},
                                                                     {"text": "Away lost 3", "kind": "sourced", "sources": [{"url": "https://form.test/b", "title": "B"}]}]},
    {"angle": "Injuries", "question": "q2", "kind": "evidence", "claims": [{"text": "Home keeper doubtful", "kind": "sourced", "sources": [{"url": "https://form.test/a", "title": "A"}]}]},
]


def old_run(engine, hours_ago=9):
    with DbSession(engine) as db:
        run = Run(id="old", event_ticker="KX-1", event_title="A vs B", status="done", result={"findings": FINDINGS}, created_at=NOW - timedelta(hours=hours_ago),
                  finished_at=NOW - timedelta(hours=hours_ago))
        db.add(run)
        db.flush()
        db.add(Run(id="new", event_ticker="KX-1", event_title="A vs B", status="running", refresh_of="old"))
        db.add_all([SourcePage(run_id="old", url=u, title=t, retrieved_at=NOW, fetch_status="ok", fetch_method="plain", final_url=f, content_hash=u, content="c", page_text=f"text of {u}", page_text_hash=u)
                    for u, t, f in (("https://form.test/a", "A", "https://form.test/a2"), ("https://form.test/b", "B", None))])
        db.add_all([ClaimCheck(run_id="old", finding_index=fi, claim_index=ci, source_url=u, verdict=v, reason="why", model="m")
                    for fi, ci, u, v in ((0, 0, "https://form.test/a", "supported"), (0, 1, "https://form.test/b", "not_supported"), (1, 0, "https://form.test/a", "supported"))])
        db.commit()


@needs_db
def test_the_earlier_evidence_is_copied_with_remapped_indices_labels_and_no_new_work(fresh_db):
    command.upgrade(alembic_config(), "head")
    old_run(fresh_db)
    carried = carry_over(fresh_db, "old", "new", new_count=1, now=NOW)
    assert [f["angle"] for f in carried] == ["Earlier research (9 hours ago): Form", "Earlier research (9 hours ago): Injuries"]
    assert all(f["carried_from"] == "old" for f in carried) and carried[0]["claims"] == FINDINGS[0]["claims"]  # the claims themselves are unchanged
    assert FINDINGS[0]["angle"] == "Form"  # the earlier run's own findings are not touched
    with DbSession(fresh_db) as db:
        checks = db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == "new").order_by(ClaimCheck.finding_index, ClaimCheck.claim_index)).all()
        assert [(c.finding_index, c.claim_index, c.source_url, c.verdict) for c in checks] == [
            (1, 0, "https://form.test/a", "supported"), (1, 1, "https://form.test/b", "not_supported"), (2, 0, "https://form.test/a", "supported")]  # shifted by the one new finding
        pages = {p.url: p for p in db.scalars(select(SourcePage).where(SourcePage.run_id == "new")).all()}
        assert set(pages) == {"https://form.test/a", "https://form.test/b"} and pages["https://form.test/a"].page_text == "text of https://form.test/a" and pages["https://form.test/a"].final_url == "https://form.test/a2"
        assert pages["https://form.test/a"].fetch_status == "ok"  # already read: not fetched again
        assert len(db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == "old")).all()) == 3  # the old run keeps its rows


@needs_db
def test_the_age_label_reads_naturally(fresh_db):
    command.upgrade(alembic_config(), "head")
    old_run(fresh_db, hours_ago=0.2)
    assert carry_over(fresh_db, "old", "new", 0, NOW)[0]["angle"].startswith("Earlier research (less than an hour ago)")


@needs_db
def test_new_findings_do_not_duplicate_the_pages_that_were_carried_over(fresh_db):
    command.upgrade(alembic_config(), "head")
    old_run(fresh_db)
    carry_over(fresh_db, "old", "new", 1, NOW)
    new = [{"angle": "Late team news", "question": "q", "kind": "evidence", "claims": [
        {"text": "Away captain out", "kind": "sourced", "sources": [{"url": "https://late.test/x", "title": "L"}, {"url": "https://form.test/a", "title": "A"}]}]}]
    with DbSession(fresh_db) as db:
        save_sources(db, "new", new, NOW, skip_urls={"https://form.test/a", "https://form.test/b"})
        urls = [p.url for p in db.scalars(select(SourcePage).where(SourcePage.run_id == "new").order_by(SourcePage.id)).all()]
    assert sorted(urls) == ["https://form.test/a", "https://form.test/b", "https://late.test/x"]  # a page cited by both is saved once
