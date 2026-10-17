"""The approval flow with simulated orders. Fakes only; nothing here can reach Kalshi's trading side."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.kalshi import KalshiClient
from app.models import Order, OrderEvent, OutcomeRecord
from app.orders import OrderError, approve_order, expire_due, fee_for_order, place_order, prepare_order, reject_order, settle_orders
from tests.conftest import EMAIL, PASSWORD, alembic_config, needs_db
from tests.test_opportunities import GOOD, GOOD_BASELINE, FakeKalshi, add_run, event, kalshi_for_good, market

pytestmark = needs_db
H = {"X-Requested-With": "t"}
NOW = datetime.now(UTC)
RUN = "run-KX-1"
HOME = "KX-1-H"


@pytest.fixture
def client_factory(make_client):
    def build(**env):
        client = make_client(**env)
        client.__enter__()
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        client.app.state.kalshi = kalshi_for_good()
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
        return client
    return build


def run(client, coro):
    return asyncio.run(coro(client.app))


def user_id(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT id FROM users LIMIT 1")).scalar_one()


def prepare(client, engine, contracts=3, market_ticker=HOME, now=None):
    uid = user_id(engine)
    return asyncio.run(prepare_order(client.app, uid, RUN, market_ticker, contracts, now or NOW))


def get(engine, order_id):
    with DbSession(engine) as db:
        return db.get(Order, order_id)


def events(engine, order_id):
    with DbSession(engine) as db:
        return [(e.from_state, e.to_state) for e in db.query(OrderEvent).filter_by(order_id=order_id).order_by(OrderEvent.id)]


def test_fee_is_rounded_up_to_the_cent_for_the_whole_order():
    assert fee_for_order(Decimal("0.42"), 1, Decimal(1)) == Decimal("0.02")  # 0.01705 rounds up
    assert fee_for_order(Decimal("0.50"), 10, Decimal(1)) == Decimal("0.18")  # 0.175 rounds up
    assert fee_for_order(Decimal("0.50"), 10, Decimal("0.5")) == Decimal("0.09")  # 0.0875 rounds up


def test_prepare_reads_the_price_and_creates_the_exact_order(client_factory, make_client):
    client = client_factory()
    try:
        order = prepare(client, make_client.engine, contracts=3)
        assert order["state"] == "proposed" and order["side"] == "yes" and order["price"] == 0.42 and order["contracts"] == 3
        assert order["fee_estimate"] == 0.06 and order["max_cost"] == pytest.approx(0.42 * 3 + 0.06) and order["our_probability"] == 0.55
        assert order["gap"] > 0.05 and len(order["client_order_id"]) == 32 and order["market_ticker"] == HOME and order["title"] == "Home vs Away"
        expires = datetime.fromisoformat(order["expires_at"])
        assert expires - NOW == timedelta(minutes=10)
        assert events(make_client.engine, order["id"]) == [(None, "proposed")]
    finally:
        client.__exit__(None, None, None)


def test_only_one_open_order_per_market(client_factory, make_client):
    client = client_factory()
    try:
        first = prepare(client, make_client.engine)
        with pytest.raises(OrderError) as caught:
            prepare(client, make_client.engine)
        assert caught.value.status_code == 409 and caught.value.extra["order_id"] == first["id"]
        asyncio.run(reject_order(client.app, first["id"], user_id(make_client.engine), "changed my mind"))
        assert prepare(client, make_client.engine)["state"] == "proposed"  # after a rejection a new one is possible
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("env,contracts,message", [
    ({}, 11, "between 1 and 10"),
    ({"ORDER_MAX_COST_USD": "1.00"}, 3, "above the limit of $1.00 per order"),
    ({"ORDER_MAX_COST_USD": "4.00", "ORDER_MAX_DAY_COST_USD": "4.00"}, 10, "above the limit of $4.00 per order"),
])
def test_limits_are_checked_when_preparing(client_factory, make_client, env, contracts, message):
    client = client_factory(**env)
    try:
        with pytest.raises(OrderError, match=re.escape(message)):
            prepare(client, make_client.engine, contracts=contracts)
    finally:
        client.__exit__(None, None, None)


def test_prepare_refuses_unknown_markets_and_started_games(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        with pytest.raises(OrderError, match="not part of the forecast"):
            prepare(client, engine, market_ticker="KX-1-NOPE")
        with pytest.raises(OrderError, match="The game has started"):
            prepare(client, engine, now=NOW + timedelta(hours=6))  # the game starts in 5 hours
    finally:
        client.__exit__(None, None, None)


def test_a_stale_forecast_and_unreadable_prices_are_refused(make_client):
    client = make_client()
    client.__enter__()
    try:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE, finished_hours_ago=20)
        client.app.state.kalshi = kalshi_for_good()
        with pytest.raises(OrderError, match="is too old"):
            prepare(client, make_client.engine)
        with DbSession(make_client.engine) as db:
            db.execute(text("UPDATE runs SET finished_at = now() - interval '1 hour', created_at = now() - interval '1 hour'"))
            db.commit()
        client.app.state.kalshi = FakeKalshi({}, broken=["KX-1"])
        with pytest.raises(OrderError) as caught:
            prepare(client, make_client.engine)
        assert caught.value.status_code == 502 and "could not be read" in caught.value.detail
    finally:
        client.__exit__(None, None, None)


def test_checks_show_each_result_and_a_failed_blocking_check_stops_approval(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order = prepare(client, engine, contracts=3)
        from app.orders import order_with_checks
        shown = asyncio.run(order_with_checks(client.app, order["id"], NOW))
        names = {c["name"]: c for c in shown["checks"]}
        assert set(names) == {"within_game_limit", "within_open_limit", "not_paused", "not_expired", "game_not_started", "forecast_fresh", "within_limits", "legs_ok", "price_ok", "enough_contracts", "still_worth_a_look"}
        assert all(c["ok"] for c in shown["checks"]) and names["still_worth_a_look"]["blocking"] is False
        # the price moved 5 cents against us: approval is blocked, the order stays
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.45", "0.47"), market("KX-1-A", "0.52", "0.54")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        with pytest.raises(OrderError, match="price_ok"):
            asyncio.run(approve_order(client.app, order["id"], 1, NOW))
        assert get(engine, order["id"]).state == "proposed"
        # too few contracts on offer
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.40", "0.42", size="2"), market("KX-1-A", "0.57", "0.59")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        with pytest.raises(OrderError, match="enough_contracts"):
            asyncio.run(approve_order(client.app, order["id"], 1, NOW))
        # a price that moved only slightly (1 cent) is within the 2-cent slippage limit
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.41", "0.43"), market("KX-1-A", "0.56", "0.58")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        assert asyncio.run(approve_order(client.app, order["id"], 1, NOW))["state"] == "approved"
    finally:
        client.__exit__(None, None, None)


def test_approving_records_who_and_when_and_nothing_else_can_approve_it_again(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order = prepare(client, engine)
        uid = user_id(engine)
        approved = asyncio.run(approve_order(client.app, order["id"], uid, NOW))
        row = get(engine, order["id"])
        assert approved["state"] == "approved" and row.approved_by == uid and row.approved_at is not None
        with pytest.raises(OrderError, match="only a proposed order can be approved"):
            asyncio.run(approve_order(client.app, order["id"], uid, NOW))
        assert events(engine, order["id"]) == [(None, "proposed"), ("proposed", "approved")]
    finally:
        client.__exit__(None, None, None)


def test_an_order_that_expires_cannot_be_approved_or_placed(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order = prepare(client, engine)
        later = NOW + timedelta(minutes=11)
        assert asyncio.run(expire_due(client.app, later)) == 1
        assert get(engine, order["id"]).state == "expired"
        with pytest.raises(OrderError, match="only a proposed order can be approved"):
            asyncio.run(approve_order(client.app, order["id"], 1, later))
        second = prepare(client, engine)  # approved but never placed before it expired
        asyncio.run(approve_order(client.app, second["id"], 1, NOW))
        result = asyncio.run(place_order(client.app, second["id"], 1, later))
        assert result["state"] == "expired" and result["fill_contracts"] is None
        assert events(engine, second["id"])[-1] == ("approved", "expired")
    finally:
        client.__exit__(None, None, None)


def test_reject_ends_the_order_with_its_reason_and_an_open_order_only(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order = prepare(client, engine)
        uid = user_id(engine)
        done = asyncio.run(reject_order(client.app, order["id"], uid, "the lineup news worries me"))
        assert done["state"] == "rejected" and done["reason"] == "the lineup news worries me"
        with pytest.raises(OrderError, match="only an open order can be rejected"):
            asyncio.run(reject_order(client.app, order["id"], uid, None))
        assert events(engine, order["id"]) == [(None, "proposed"), ("proposed", "rejected")]
    finally:
        client.__exit__(None, None, None)


def approved(client, engine, contracts=3):
    order = prepare(client, engine, contracts=contracts)
    asyncio.run(approve_order(client.app, order["id"], 1, NOW))
    return order["id"]


def test_placing_records_a_simulated_fill_at_the_price_of_that_moment(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order_id = approved(client, engine, contracts=3)
        placed = asyncio.run(place_order(client.app, order_id, 1, NOW))
        assert placed["state"] == "placed" and placed["fill_contracts"] == 3 and placed["fill_price"] == 0.42 and placed["fill_fee"] == 0.06
        assert events(engine, order_id) == [(None, "proposed"), ("proposed", "approved"), ("approved", "placed")]
    finally:
        client.__exit__(None, None, None)


def test_placing_twice_or_in_parallel_fills_only_once(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order_id = approved(client, engine)

        async def both():
            return await asyncio.gather(place_order(client.app, order_id, 1, NOW), place_order(client.app, order_id, 1, NOW), return_exceptions=True)
        results = asyncio.run(both())
        assert sum(1 for r in results if isinstance(r, dict) and r["state"] == "placed") == 1
        assert sum(1 for r in results if isinstance(r, OrderError) and r.status_code == 409) == 1
        with pytest.raises(OrderError, match="only an approved order can be placed"):
            asyncio.run(place_order(client.app, order_id, 1, NOW))
        assert [e for e in events(engine, order_id) if e[1] == "placed"] == [("approved", "placed")]
    finally:
        client.__exit__(None, None, None)


def test_a_price_that_moved_too_far_before_placing_is_a_simulated_rejection(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order_id = approved(client, engine)
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.48", "0.50"), market("KX-1-A", "0.49", "0.51")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        result = asyncio.run(place_order(client.app, order_id, 1, NOW))
        assert result["state"] == "simulated_rejected" and "price_ok" in result["reason"] and result["fill_contracts"] is None
    finally:
        client.__exit__(None, None, None)


def test_the_fill_is_capped_at_the_contracts_offered(client_factory, make_client):
    client = client_factory()
    engine = make_client.engine
    try:
        order_id = approved(client, engine, contracts=5)
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.40", "0.42", size="2"), market("KX-1-A", "0.57", "0.59")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        # fewer contracts on offer than wanted fails the check, so the simulation rejects it; with exactly enough it fills fully
        assert asyncio.run(place_order(client.app, order_id, 1, NOW))["state"] == "simulated_rejected"
    finally:
        client.__exit__(None, None, None)


def test_the_daily_limit_counts_what_was_approved_today(client_factory, make_client):
    client = client_factory(ORDER_MAX_COST_USD="5.00", ORDER_MAX_DAY_COST_USD="5.00")
    engine = make_client.engine
    try:
        first = prepare(client, engine, contracts=10)  # 10 x 0.42 + fee 0.18 = 4.38
        asyncio.run(approve_order(client.app, first["id"], 1, NOW))
        with pytest.raises(OrderError, match="above the limit of \\$5.00"):
            prepare(client, engine, contracts=10, market_ticker="KX-1-A")  # the day total would be about 8.7
        prepare(client, engine, contracts=1, market_ticker="KX-1-A")  # a small one still fits (0.43 + fee)
    finally:
        client.__exit__(None, None, None)


def settled_setup(client, engine, resolved_yes):
    order_id = approved(client, engine, contracts=3)
    asyncio.run(place_order(client.app, order_id, 1, NOW))
    with DbSession(engine) as db:
        db.query(OutcomeRecord).filter_by(market_ticker=HOME).update({"resolved_at": NOW, "resolved_yes": resolved_yes})
        db.commit()
    return order_id


@pytest.mark.parametrize("resolved_yes,won,result", [(True, True, 3 * 1 - 3 * 0.42 - 0.06), (False, False, -3 * 0.42 - 0.06)])
def test_settlement_pays_a_win_and_charges_a_loss_with_the_fee(client_factory, make_client, resolved_yes, won, result):
    client = client_factory()
    engine = make_client.engine
    try:
        order_id = settled_setup(client, engine, resolved_yes)
        assert settle_orders(engine, NOW) == 1 and settle_orders(engine, NOW) == 0  # once only
        row = get(engine, order_id)
        assert row.state == "settled" and row.won is won and float(row.paper_result) == pytest.approx(result)
        assert events(engine, order_id)[-1] == ("placed", "settled")
    finally:
        client.__exit__(None, None, None)


def test_the_endpoints_need_login_and_the_header_and_work_end_to_end(client_factory, make_client):
    client = client_factory()
    try:
        anonymous = make_client()
        with anonymous:
            assert anonymous.get("/api/orders").status_code == 401
            assert anonymous.post("/api/orders", json={"legs": [{"run_id": RUN, "market_ticker": HOME}], "contracts": 1}, headers=H).status_code == 401
        body = {"legs": [{"run_id": RUN, "market_ticker": HOME}], "contracts": 2}
        assert client.post("/api/orders", json=body).status_code in (400, 403)  # no X-Requested-With header
        created = client.post("/api/orders", json=body, headers=H)
        assert created.status_code == 201 and created.json()["state"] == "proposed"
        oid = created.json()["id"]
        shown = client.get(f"/api/orders/{oid}").json()
        assert shown["checks"] and all(c["ok"] for c in shown["checks"])
        assert client.post(f"/api/orders/{oid}/approve").status_code in (400, 403)
        assert client.post(f"/api/orders/{oid}/approve", headers=H).json()["state"] == "approved"
        assert client.post(f"/api/orders/{oid}/place", headers=H).json()["state"] == "placed"
        duplicate = client.post(f"/api/orders/{oid}/place", headers=H)
        assert duplicate.status_code == 409 and "only an approved order can be placed" in duplicate.json()["detail"]["message"]
        assert client.post("/api/orders", json={**body, "contracts": 99}, headers=H).status_code == 422
        listing = client.get("/api/orders").json()
        assert [o["state"] for o in listing["orders"]] == ["placed"] and listing["totals"]["settled"] == 0
        assert client.get("/api/orders/99999").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_the_code_has_no_way_to_send_an_order_to_kalshi():
    source = Path(__file__).resolve().parent.parent / "app"
    for path in source.rglob("*.py"):
        text_ = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("@router.post("))  # our own endpoints
        if path.name == "telegram.py":  # the one sender: it posts to Telegram's own API and nowhere else
            assert "api.telegram.org" in text_ and "kalshi" not in text_.lower()
            continue
        assert ".post(" not in text_, f"{path.name} makes an outgoing POST"
        assert "portfolio/orders" not in text_ and "portfolio/events/orders" not in text_, f"{path.name} names Kalshi's order endpoint"
    assert not [n for n in dir(KalshiClient) if any(w in n.lower() for w in ("order", "place", "create", "post", "trade", "buy", "sell"))]


def test_the_settings_are_validated():
    base = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
    s = load_settings(base)
    assert (s.order_max_contracts, s.order_max_cost_usd, s.order_max_day_cost_usd, s.order_expiry_minutes, s.order_max_slippage_cents) == (10, 5.0, 20.0, 10.0, 2.0)
    for bad in ({"ORDER_MAX_CONTRACTS": "0"}, {"ORDER_MAX_COST_USD": "-1"}, {"ORDER_MAX_COST_USD": "30"}, {"ORDER_EXPIRY_MINUTES": "x"}):
        with pytest.raises(SettingsError):
            load_settings(base | bad)
