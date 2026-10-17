"""Bets on the same game count as one risk: the per-game and the all-open limits of the risk framework."""

import asyncio
import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Order, OrderLeg, Run
from app.orders import OrderError, approve_order, open_exposure, place_order
from tests.conftest import needs_db
from tests.test_orders import HOME, NOW, client_factory, prepare, user_id  # noqa: F401  (the fixture and helpers of the order tests)

pytestmark = needs_db
AWAY, TOTAL = "KX-1-A", "KXTTOTAL-1-1"  # the same game as HOME: the winner's other side, and a total market researched in the same run
ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
WIDE = {"ORDER_MAX_COST_USD": "5.00", "ORDER_MAX_DAY_COST_USD": "50.00"}  # the existing limits do not get in the way


def test_the_limits_are_off_by_default_and_a_bad_value_is_refused():
    s = load_settings(ENV)
    assert s.order_max_game_cost_usd == 0 and s.order_max_open_cost_usd == 0
    for name, bad in (("ORDER_MAX_GAME_COST_USD", "-3"), ("ORDER_MAX_OPEN_COST_USD", "lots")):
        with pytest.raises(SettingsError, match=name):
            load_settings(ENV | {name: bad})


def test_orders_of_different_markets_of_one_game_are_one_risk(client_factory, make_client):
    client = client_factory(ORDER_MAX_GAME_COST_USD="2.5", **WIDE)
    engine = make_client.engine
    try:
        first = prepare(client, engine, contracts=3)  # about 1.3
        asyncio.run(approve_order(client.app, first["id"], user_id(engine), NOW))
        with pytest.raises(OrderError, match="more on one game than the limit allows: .*on this game together \\(limit \\$2.50\\)"):
            prepare(client, engine, contracts=3, market_ticker=AWAY)  # about 1.3 + 1.4: above 2.5
        small = prepare(client, engine, contracts=1, market_ticker=AWAY)  # about 0.45: 1.75 together, fits
        assert small["state"] == "proposed"
        with pytest.raises(OrderError, match="on this game together"):
            prepare(client, engine, contracts=3, market_ticker=TOTAL)  # a total market of the same game (found through its run) counts too
    finally:
        client.__exit__(None, None, None)


def test_the_open_limit_counts_all_open_orders_and_a_settled_order_is_not_open(client_factory, make_client):
    client = client_factory(ORDER_MAX_OPEN_COST_USD="2.5", **WIDE)
    engine = make_client.engine
    try:
        first = prepare(client, engine, contracts=3)
        asyncio.run(approve_order(client.app, first["id"], user_id(engine), NOW))
        with pytest.raises(OrderError, match="open orders above the limit: .*open together \\(limit \\$2.50\\)"):
            prepare(client, engine, contracts=3, market_ticker=AWAY)
        with DbSession(engine) as db:  # the first order ends: it is no longer open
            db.get(Order, first["id"]).state = "settled"
            db.commit()
        assert prepare(client, engine, contracts=3, market_ticker=AWAY)["state"] == "proposed"
    finally:
        client.__exit__(None, None, None)


def test_approving_and_placing_are_blocked_by_the_limits(client_factory, make_client):
    client = client_factory(**WIDE)
    engine = make_client.engine
    try:
        first = prepare(client, engine, contracts=3)
        second = prepare(client, engine, contracts=3, market_ticker=AWAY)  # both fit while there is no limit
        client.app.state.settings = replace(client.app.state.settings, order_max_game_cost_usd=2.5)
        asyncio.run(approve_order(client.app, first["id"], user_id(engine), NOW))  # alone it fits
        with pytest.raises(OrderError, match="within_game_limit"):
            asyncio.run(approve_order(client.app, second["id"], user_id(engine), NOW))
        client.app.state.settings = replace(client.app.state.settings, order_max_game_cost_usd=0.0)
        asyncio.run(approve_order(client.app, second["id"], user_id(engine), NOW))  # both approved, no limit
        client.app.state.settings = replace(client.app.state.settings, order_max_open_cost_usd=2.5)
        placed = asyncio.run(place_order(client.app, second["id"], user_id(engine), NOW))  # the other order is open at about 1.3: together over 2.5
        assert placed["state"] == "simulated_rejected" and "within_open_limit" in placed["reason"]
    finally:
        client.__exit__(None, None, None)


def test_exposure_by_state_and_a_ticket_counts_in_full_against_every_game(client_factory, make_client):
    client_factory()
    engine = make_client.engine

    counter = iter(range(1000))

    def add(state, cost, games, fill=None):
        n = next(counter)  # one open leg per market is a database rule: every order gets its own markets
        with DbSession(engine) as db:
            order = Order(
                client_order_id=uuid.uuid4().hex, run_id="r-" + games[0], event_ticker=games[0], market_ticker=f"{games[0]}-M{n}", outcome="x", title="x", side="yes", price=Decimal("0.5"),
                contracts=1, max_cost=Decimal(str(cost)), fee_estimate=Decimal("0"), our_probability=Decimal("0.6"), gap=Decimal("0.05"), state=state,
                expires_at=NOW + timedelta(hours=1), fill_price=None if fill is None else Decimal(str(fill)), fill_contracts=None if fill is None else Decimal(1),
                fill_fee=None if fill is None else Decimal("0"))
            db.add(order)
            db.flush()
            for position, game in enumerate(games):
                if db.get(Run, "r-" + game) is None:
                    db.add(Run(id="r-" + game, event_ticker=game, event_title=game, status="done"))
                db.flush()
                db.add(OrderLeg(order_id=order.id, position=position, run_id="r-" + game, event_ticker=f"{game}-G{n}", market_ticker=f"{game}-M{n}", outcome="x", title="x",
                                side="yes", price=Decimal("0.5"), our_probability=Decimal("0.6")))
            db.commit()

    add("approved", 1.00, ["GAME-A"])              # counts at its maximum cost
    add("placed", 99, ["GAME-A"], fill=0.40)        # counts at what it cost (0.40), not its maximum
    add("approved", 2.00, ["GAME-A", "GAME-B"])    # a ticket: in full against both games
    for state in ("settled", "rejected", "expired", "proposed", "simulated_rejected"):
        add(state, 50, ["GAME-C"])                  # none of these is open
    with DbSession(engine) as db:
        total, per_game = open_exposure(db)
    assert total == Decimal("3.40") and per_game == {"GAME-A": Decimal("3.40"), "GAME-B": Decimal("2.00")}
