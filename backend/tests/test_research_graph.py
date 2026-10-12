import asyncio
import logging

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.config import load_settings
from app.research.graph import EmptyPlanError, build_graph
from app.research.prompts import PLANNER_INSTRUCTIONS
from app.research.schemas import MarketInfo
from tests.fakes import FakeModel

ENV = {
    "DATABASE_URL": "postgresql://u:p@db:5432/x",
    "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
    "SESSION_SECRET": "s" * 40,
    "OPENAI_API_KEY": "sk-test",
}
MARKET = {"ticker": "KX-1", "title": "Will Team A beat Team B?", "subtitle": None, "close_time": None, "rules": None, "price_dollars": "0.48"}


def run(model, **settings):
    loaded = load_settings({**ENV, **{k: str(v) for k, v in settings.items()}})
    graph = build_graph(model, loaded, MemorySaver())
    config = {"configurable": {"thread_id": "t"}, "max_concurrency": loaded.max_researchers, "recursion_limit": 10}
    return asyncio.run(graph.ainvoke({"market": MARKET}, config))


def test_planner_gets_the_market_and_the_cap():
    model = FakeModel()
    state = run(model, MAX_RESEARCHERS=4)
    market, cap = model.plan_calls[0]
    assert isinstance(market, MarketInfo) and market.title == "Will Team A beat Team B?" and cap == 4
    assert [a["name"] for a in state["angles"]] == ["Form", "Injuries"]
    assert state["cut_angles"] == 0


def test_too_many_angles_are_cut_to_the_cap_and_the_cut_is_recorded(caplog):
    caplog.set_level(logging.WARNING, logger="app.research")
    state = run(FakeModel(angle_names=list("ABCDEF")), MAX_RESEARCHERS=3)
    assert [a["name"] for a in state["angles"]] == ["A", "B", "C"]
    assert state["cut_angles"] == 3
    assert "dropping 3" in caplog.text  # visible, not silent


def test_empty_plan_fails_the_run_clearly():
    with pytest.raises(EmptyPlanError, match="no research angles"):
        run(FakeModel(angle_names=[]))


def test_planner_usage_is_recorded():
    state = run(FakeModel())
    assert state["usages"][0]["model"] == "gpt-5.4-mini" and state["usages"][0]["input_tokens"] == 1000


def test_planner_instructions_are_written_for_the_clients_sports_and_forbid_predictions():
    text = PLANNER_INSTRUCTIONS.format(max_angles=4, today="2026-10-12")
    for word in ("soccer", "baseball", "tennis", "starting pitchers", "surface", "lineups", "odds"):
        assert word in text
    assert "never state a probability" in text


def test_one_researcher_per_angle_running_in_parallel_within_the_cap():
    model = FakeModel(angle_names=list("ABCDEF"), delay=0.1)
    state = run(model, MAX_RESEARCHERS=3)
    assert sorted(model.research_calls) == ["A", "B", "C"]  # only the kept angles
    assert 1 < model.max_running <= 3  # parallel, but never above the cap
    assert sorted(f["angle"] for f in state["findings"]) == ["A", "B", "C"]


def test_findings_carry_claims_with_real_citations_and_clean_text():
    model = FakeModel(angle_names=["Form"], lines={"Form": [("Team A won five straight", "https://bbc.test/x"), ("No source here", None)]})
    f = run(model)["findings"][0]
    first, second = f["claims"]
    assert first == {"text": "Team A won five straight", "kind": "sourced",
                     "sources": [{"url": "https://bbc.test/x", "title": "Page https://bbc.test/x"}]}
    assert second["kind"] == "uncited" and second["sources"] == []


def test_usage_is_collected_from_every_call():
    state = run(FakeModel(angle_names=["A", "B"]))
    assert len(state["usages"]) == 3  # planner + 2 researchers
    assert [u["model"] for u in state["usages"]].count("gpt-5.4") == 2
    assert sum(u["search_calls"] for u in state["usages"]) == 4


def test_one_failing_researcher_does_not_stop_the_others(caplog):
    caplog.set_level(logging.WARNING, logger="app.research")
    state = run(FakeModel(angle_names=["A", "B", "C"], fail={"B"}))
    assert sorted(f["angle"] for f in state["findings"]) == ["A", "C"]
    assert state["errors"] == [{"angle": "B", "error": "Researcher call failed: boom for B"}]
    assert "Researcher for angle 'B' failed" in caplog.text


def test_every_researcher_failing_leaves_errors_and_no_findings():
    state = run(FakeModel(angle_names=["A", "B"], fail={"A", "B"}))
    assert state.get("findings", []) == [] and len(state["errors"]) == 2


def test_an_unexpected_crash_is_recorded_and_logged_not_hidden(caplog):
    class Crashy(FakeModel):
        async def research(self, market, angle):
            raise KeyError("oops")

    state = run(Crashy(angle_names=["A"]))
    assert state["errors"][0]["error"].startswith("KeyError")
    assert "crashed" in caplog.text


def test_an_answer_without_findings_is_an_error_but_still_counted_for_cost():
    from app.research.schemas import ResearchOutput, TextSegment, Usage

    class Chatty(FakeModel):
        async def research(self, market, angle):
            return ResearchOutput(segments=[TextSegment(text="I could not find anything useful.")], usage=Usage("gpt-5.4", 100, 0, 10, 1))

    state = run(Chatty(angle_names=["A"]))
    assert state["errors"] == [{"angle": "A", "error": "The answer contained no findings"}]
    assert len(state["usages"]) == 2  # planner and the paid-for researcher call
