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
    graph = build_graph(model, load_settings({**ENV, **{k: str(v) for k, v in settings.items()}}), MemorySaver())
    config = {"configurable": {"thread_id": "t"}}
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
