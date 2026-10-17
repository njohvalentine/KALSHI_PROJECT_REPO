"""The stop rules of the risk framework: no new simulated order after the simulated results lose too much."""

import asyncio
import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Order
from app.orders import OrderError, approve_order, pause_reason, place_order
from tests.test_orders import HOME, NOW, RUN, client_factory, prepare, user_id  # noqa: F401  (the fixture and helpers of the order tests)
from tests.conftest import needs_db

pytestmark = needs_db
ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}


def settled(engine, result, hours_ago=1.0, placed_days_ago=0.0):
    with DbSession(engine) as db:
        db.add(Order(
            client_order_id=uuid.uuid4().hex, run_id="r", event_ticker="KX-9", market_ticker="KX-9-H", outcome="x", title="x", side="yes", price=Decimal("0.5"), contracts=1,
            max_cost=Decimal("0.5"), fee_estimate=Decimal("0.02"), our_probability=Decimal("0.6"), gap=Decimal("0.05"), state="settled", expires_at=NOW,
            placed_at=NOW - timedelta(days=placed_days_ago), settled_at=NOW - timedelta(hours=hours_ago), paper_result=Decimal(str(result))))
        db.commit()


def reason(engine, **env):
    with DbSession(engine) as db:
        return pause_reason(db, load_settings(ENV | {k: str(v) for k, v in env.items()}), NOW)


def test_the_settings_are_off_by_default_and_a_bad_value_is_refused():
    s = load_settings(ENV)
    assert s.order_pause_day_loss_usd == 0 and s.order_pause_total_loss_usd == 0 and s.order_loss_since is None
    for name, bad in (("ORDER_PAUSE_DAY_LOSS_USD", "-1"), ("ORDER_PAUSE_TOTAL_LOSS_USD", "ten"), ("ORDER_LOSS_SINCE", "yesterday")):
        with pytest.raises(SettingsError, match=name):
            load_settings(ENV | {name: bad})


def test_with_the_rules_off_no_loss_pauses_anything(client_factory, make_client):
    client_factory()
    settled(make_client.engine, -50)
    assert reason(make_client.engine) is None


def test_the_day_rule_counts_the_last_24_hours_and_wins_offset_losses(client_factory, make_client):
    client_factory()
    engine = make_client.engine
    settled(engine, -6, hours_ago=2)
    settled(engine, -3.99, hours_ago=5)
    assert reason(engine, ORDER_PAUSE_DAY_LOSS_USD="10") is None  # 9.99 is below 10
    settled(engine, -0.01, hours_ago=6)
    text = reason(engine, ORDER_PAUSE_DAY_LOSS_USD="10")
    assert "Paused" in text and "last 24 hours are -$10.00" in text and "ORDER_PAUSE_DAY_LOSS_USD" in text
    settled(engine, 4, hours_ago=1)  # a win offsets
    assert reason(engine, ORDER_PAUSE_DAY_LOSS_USD="10") is None
    settled(engine, -100, hours_ago=30)  # older than a day: not in the day rule
    assert reason(engine, ORDER_PAUSE_DAY_LOSS_USD="10") is None


def test_the_total_rule_counts_everything_since_the_restart_date(client_factory, make_client):
    client_factory()
    engine = make_client.engine
    settled(engine, -15, hours_ago=100, placed_days_ago=5)
    settled(engine, -6, hours_ago=100, placed_days_ago=2)
    assert "Paused" in reason(engine, ORDER_PAUSE_TOTAL_LOSS_USD="20")  # 21 lost
    restart = (NOW - timedelta(days=3)).strftime("%Y-%m-%d")
    assert reason(engine, ORDER_PAUSE_TOTAL_LOSS_USD="20", ORDER_LOSS_SINCE=restart) is None  # after the restart only 6 is lost
    assert "since" in reason(engine, ORDER_PAUSE_TOTAL_LOSS_USD="5", ORDER_LOSS_SINCE=restart)


def test_preparing_is_refused_while_paused_and_approving_and_placing_are_blocked(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    order = prepare(client, engine, contracts=1)  # prepared before the stop rule
    settled(engine, -3, hours_ago=1)
    client.app.state.settings = replace(client.app.state.settings, order_pause_day_loss_usd=1.0)
    try:
        with pytest.raises(OrderError, match="Paused: the simulated results of the last 24 hours are -\\$3.00"):
            prepare(client, engine, contracts=1, market_ticker="KX-1-A")
        with pytest.raises(OrderError, match="not_paused"):
            asyncio.run(approve_order(client.app, order["id"], user_id(engine), NOW))
        # the stop rule is lifted: approving and placing work again
        client.app.state.settings = replace(client.app.state.settings, order_pause_day_loss_usd=0.0)
        approved = asyncio.run(approve_order(client.app, order["id"], user_id(engine), NOW))
        assert approved["state"] == "approved"
        client.app.state.settings = replace(client.app.state.settings, order_pause_day_loss_usd=1.0)
        placed = asyncio.run(place_order(client.app, order["id"], user_id(engine), NOW))  # a failed blocking check at placing rejects the order in the simulation
        assert placed["state"] == "simulated_rejected" and "not_paused" in placed["reason"]
    finally:
        client.__exit__(None, None, None)
