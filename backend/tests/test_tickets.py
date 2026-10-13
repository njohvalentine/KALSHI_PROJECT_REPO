"""Tickets of several games (combos), simulated. Fakes only; nothing here can reach Kalshi's trading side."""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy.orm import Session as DbSession

from app.models import Order, OrderLeg, OutcomeRecord
from app.orders import OrderError, approve_order, place_order, prepare_ticket, reject_order, settle_orders
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.test_opportunities import GOOD, GOOD_BASELINE, FakeKalshi, add_run, event, market, outcome, prediction
from tests.test_orders import H, NOW, user_id

pytestmark = needs_db
SECOND = prediction(outcome("KX-3-H", "Two wins", 0.60, 0.55, 0.65), outcome("KX-3-A", "Three wins", 0.40, 0.35, 0.45))


@pytest.fixture
def client(make_client):
    c = make_client()
    c.__enter__()
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
    c.app.state.kalshi = FakeKalshi({
        "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.40", "0.42"), market("KX-1-A", "0.57", "0.59")),
        "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        "KX-3": event("KX-3", "KXTGAME", market("KX-3-H", "0.48", "0.50"), market("KX-3-A", "0.48", "0.50")),
    })
    add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    add_run(make_client.engine, "KX-3", "Two vs Three", SECOND)
    yield c
    c.__exit__(None, None, None)


def ticket(client, engine, legs, contracts=2):
    return asyncio.run(prepare_ticket(client.app, user_id(engine), contracts, legs, NOW))


TWO = [("run-KX-1", "KX-1-H"), ("run-KX-3", "KX-3-H")]


def test_a_two_leg_ticket_multiplies_prices_and_probabilities(client, make_client):
    t = ticket(client, make_client.engine, TWO)
    assert t["price"] == pytest.approx(0.42 * 0.50) and t["our_probability"] == pytest.approx(0.55 * 0.60)
    assert [g["market_ticker"] for g in t["legs"]] == ["KX-1-H", "KX-3-H"] and t["state"] == "proposed"
    assert t["gap"] == pytest.approx(0.33 - 0.21 - t["fee_estimate"] / 2, abs=1e-3)


def test_two_legs_of_one_game_or_too_many_legs_or_a_repeat_are_refused(client, make_client):
    e = make_client.engine
    with pytest.raises(OrderError, match="same game"):
        ticket(client, e, [("run-KX-1", "KX-1-H"), ("run-KX-1", "KXTTOTAL-1-1")])
    with pytest.raises(OrderError, match="twice"):
        ticket(client, e, [("run-KX-1", "KX-1-H"), ("run-KX-1", "KX-1-H")])
    client.app.state.settings = replace(client.app.state.settings, ticket_max_legs=1)
    with pytest.raises(OrderError, match="at most 1"):
        ticket(client, e, TWO)


def test_a_market_in_an_open_ticket_cannot_be_used_again_until_it_is_rejected(client, make_client):
    e = make_client.engine
    first = ticket(client, e, TWO)
    with pytest.raises(OrderError) as caught:
        ticket(client, e, [("run-KX-3", "KX-3-H")])
    assert caught.value.status_code == 409 and caught.value.extra["order_id"] == first["id"]
    asyncio.run(reject_order(client.app, first["id"], 1, None))
    assert ticket(client, e, [("run-KX-3", "KX-3-H")])["state"] == "proposed"


def test_each_leg_is_checked_and_a_moved_price_on_one_leg_blocks_approval(client, make_client):
    t = ticket(client, make_client.engine, TWO)
    client.app.state.kalshi.events["KX-3"] = event("KX-3", "KXTGAME", market("KX-3-H", "0.52", "0.55"), market("KX-3-A", "0.44", "0.46"))
    with pytest.raises(OrderError, match=r"price_ok \(leg 2\)"):
        asyncio.run(approve_order(client.app, t["id"], 1, NOW))


def test_place_records_each_legs_fill_and_frees_the_markets(client, make_client):
    e = make_client.engine
    t = ticket(client, e, TWO)
    asyncio.run(approve_order(client.app, t["id"], 1, NOW))
    placed = asyncio.run(place_order(client.app, t["id"], 1, NOW))
    assert placed["state"] == "placed" and [g["fill_price"] for g in placed["legs"]] == [0.42, 0.50]
    with DbSession(e) as db:
        assert not any(g.open for g in db.query(OrderLeg).all())


def settle_with(engine, order_id, results):
    with DbSession(engine) as db:
        for market_ticker, yes in results.items():
            db.query(OutcomeRecord).filter_by(market_ticker=market_ticker).update({"resolved_at": NOW, "resolved_yes": yes})
        db.commit()
    return settle_orders(engine, NOW)


def placed(client, engine):
    t = ticket(client, engine, TWO)
    asyncio.run(approve_order(client.app, t["id"], 1, NOW))
    asyncio.run(place_order(client.app, t["id"], 1, NOW))
    return t["id"]


@pytest.mark.parametrize("results,won", [({"KX-1-H": True, "KX-3-H": True}, True), ({"KX-1-H": True, "KX-3-H": False}, False)])
def test_a_ticket_wins_only_if_every_leg_wins(client, make_client, results, won):
    e = make_client.engine
    oid = placed(client, e)
    assert settle_with(e, oid, results) == 1
    with DbSession(e) as db:
        o = db.get(Order, oid)
        assert o.state == "settled" and o.won is won
        assert float(o.paper_result) > 0 if won else float(o.paper_result) < 0


def test_a_lost_leg_settles_at_once_and_an_unknown_leg_waits(client, make_client):
    e = make_client.engine
    oid = placed(client, e)
    assert settle_with(e, oid, {"KX-1-H": True}) == 0  # the other leg is not known yet
    assert settle_with(e, oid, {"KX-3-H": False}) == 1


def test_a_voided_leg_returns_the_stake(client, make_client):
    e = make_client.engine
    oid = placed(client, e)
    assert settle_with(e, oid, {"KX-1-H": True, "KX-3-H": None}) == 1
    with DbSession(e) as db:
        o = db.get(Order, oid)
        assert o.won is None and float(o.paper_result) == 0
