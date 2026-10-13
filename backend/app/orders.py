"""Simulated tickets (orders) and the approval flow. NOTHING IS EVER SENT TO KALSHI: there is no trading code at all.

A ticket has one or more legs (one market of one game each) and pays only if every leg wins; one leg is a plain
order. It is prepared from forecasts (state `proposed`), approved or rejected by a person, then placed in
the simulation by a separate step (`placed`: a simulated fill at the price of that moment, or
`simulated_rejected`), and settled when the game has ended. Every change of state is one atomic database
update that only one caller can win, so a double click or a retry cannot place an order twice, and every
change is written to an append-only history."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.auth import require_requested_with, require_user
from app.config import Settings
from app.models import Order, OrderEvent, OrderLeg, OutcomeRecord, User
from app.opportunities import evaluate_game, load_game
from app.research.compare import FEE_RATE

log = logging.getLogger("app.orders")

router = APIRouter(prefix="/api/orders", tags=["orders"], dependencies=[Depends(require_user)])

OPEN_STATES = ("proposed", "approved")
CENT = Decimal("0.01")


class OrderError(Exception):
    def __init__(self, status_code: int, detail: str, extra: dict | None = None):
        super().__init__(detail)
        self.status_code, self.detail, self.extra = status_code, detail, extra or {}


def fee_for_order(price: Decimal, contracts: Decimal | int, multiplier: Decimal) -> Decimal:
    """Taker fee for a whole order, rounded up to the cent (Kalshi's published formula; see the spec)."""
    raw = FEE_RATE * multiplier * Decimal(contracts) * price * (1 - price)
    return (raw / CENT).to_integral_value(rounding="ROUND_CEILING") * CENT


def _dec(value) -> Decimal:
    return Decimal(str(value))


def _utc_midnight(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _record(db: DbSession, order_id: int, from_state: str | None, to_state: str, actor: int | None, detail: str | None = None) -> None:
    db.add(OrderEvent(order_id=order_id, from_state=from_state, to_state=to_state, actor=actor, detail=detail))


def day_cost(db: DbSession, now: datetime, exclude_id: int | None = None) -> Decimal:
    """What the orders approved today (UTC) may cost in all: their maximum cost, until they are placed, then what they cost."""
    query = select(Order).where(Order.approved_at >= _utc_midnight(now), Order.state.in_(("approved", "placed", "settled")))
    if exclude_id is not None:
        query = query.where(Order.id != exclude_id)
    total = Decimal(0)
    for o in db.scalars(query):
        total += o.max_cost if o.state == "approved" else (o.fill_price or o.price) * (o.fill_contracts or 0) + (o.fill_fee or 0)
    return total


def order_to_dict(o: Order, legs: list[OrderLeg] | None = None) -> dict:
    def num(x):
        return None if x is None else float(x)

    def iso(x):
        return None if x is None else x.isoformat()

    out = {
        "id": o.id, "client_order_id": o.client_order_id, "run_id": o.run_id, "event_ticker": o.event_ticker, "market_ticker": o.market_ticker,
        "outcome": o.outcome, "title": o.title, "game_start": iso(o.game_start), "side": o.side, "price": num(o.price), "contracts": o.contracts,
        "max_cost": num(o.max_cost), "fee_estimate": num(o.fee_estimate), "our_probability": num(o.our_probability), "gap": num(o.gap),
        "forecast_at": iso(o.forecast_at), "state": o.state, "created_at": iso(o.created_at), "expires_at": iso(o.expires_at),
        "approved_at": iso(o.approved_at), "reason": o.reason, "placed_at": iso(o.placed_at), "fill_contracts": num(o.fill_contracts),
        "fill_price": num(o.fill_price), "fill_fee": num(o.fill_fee), "settled_at": iso(o.settled_at), "won": o.won, "paper_result": num(o.paper_result),
    }
    if legs is not None:
        out["legs"] = [
            {"position": g.position, "run_id": g.run_id, "event_ticker": g.event_ticker, "market_ticker": g.market_ticker, "outcome": g.outcome,
             "title": g.title, "game_start": iso(g.game_start), "side": g.side, "price": num(g.price), "our_probability": num(g.our_probability),
             "forecast_at": iso(g.forecast_at), "fill_price": num(g.fill_price), "won": g.won}
            for g in sorted(legs, key=lambda g: g.position)
        ]
    return out


def _legs_of(db: DbSession, order_id: int) -> list[OrderLeg]:
    return list(db.scalars(select(OrderLeg).where(OrderLeg.order_id == order_id).order_by(OrderLeg.position)))


def _close_legs(db: DbSession, order_id: int) -> None:
    """A ticket that is no longer proposed or approved frees its markets for a new ticket."""
    db.execute(update(OrderLeg).where(OrderLeg.order_id == order_id).values(open=False))


async def fresh_market(app, order_or_run: tuple[str, str]) -> dict:
    """Today's prices for one market of a stored forecast: {"market": comparison outcome or None, "game": stored game data}."""
    run_id, market_ticker = order_or_run
    state = app.state
    game = await asyncio.to_thread(load_game, state.engine, run_id)
    if game is None:
        raise OrderError(404, "There is no forecast for that run.")
    comparison = await evaluate_game(state.kalshi, state.settings, state.fee_cache, game)
    if "unavailable" in comparison:
        return {"market": None, "game": game, "unavailable": comparison["unavailable"]}
    market = next((c for c in comparison["outcomes"] if c["market_ticker"] == market_ticker), None)
    return {"market": market, "game": game, "unavailable": None}


def _side_price(market: dict, side: str):
    return market["yes_ask"] if side == "yes" else market["no_ask"]


def _side_size(market: dict, side: str):
    leg = market.get("yes" if side == "yes" else "no")
    return None if not leg else leg.get("size")


def _combined(prices: list[Decimal]) -> Decimal:
    out = Decimal(1)
    for p in prices:
        out *= p
    return out.quantize(Decimal("0.0001"))


def checks_for(order: Order, legs: list[OrderLeg], fresh_by_leg: list[dict], s: Settings, db: DbSession, now: datetime) -> list[dict]:
    """The checks shown on the Approval page: the ticket's, then each leg's (with `leg` set). A failed check with
    blocking true stops approving and placing."""
    minutes_left = (order.expires_at - now).total_seconds() / 60
    out = [{"name": "not_expired", "leg": None, "ok": minutes_left > 0, "blocking": True,
            "detail": f"{minutes_left:.0f} minutes left" if minutes_left > 0 else "the time limit has passed"}]
    spent = day_cost(db, now, exclude_id=order.id)
    within = (order.contracts <= s.order_max_contracts and order.max_cost <= _dec(s.order_max_cost_usd)
              and spent + order.max_cost <= _dec(s.order_max_day_cost_usd))
    out.append({"name": "within_limits", "leg": None, "ok": within, "blocking": True,
                "detail": f"{order.contracts} contracts (limit {s.order_max_contracts}), up to ${order.max_cost:.2f} (limit ${s.order_max_cost_usd:.2f}), "
                          f"${spent + order.max_cost:.2f} today (limit ${s.order_max_day_cost_usd:.2f})"})
    games = [g.event_ticker for g in legs]
    legs_ok = len(legs) <= s.ticket_max_legs and len(set(games)) == len(games)
    out.append({"name": "legs_ok", "leg": None, "ok": legs_ok, "blocking": True,
                "detail": f"{len(legs)} leg{'s' if len(legs) != 1 else ''} (limit {s.ticket_max_legs}), "
                          + ("each from a different game" if len(set(games)) == len(games) else "two legs are from the same game")})
    for leg, fresh in zip(legs, fresh_by_leg):
        game, market = fresh["game"], fresh["market"]
        n = leg.position
        age_h = None if game["finished_at"] is None else (now - game["finished_at"]).total_seconds() / 3600
        started = game["start"] is not None and game["start"] <= now
        out.append({"name": "game_not_started", "leg": n, "ok": not started, "blocking": True,
                    "detail": "the game has started" if started else ("start time unknown" if game["start"] is None
                                                                     else f"it starts in {(game['start'] - now).total_seconds() / 3600:.1f} hours")})
        out.append({"name": "forecast_fresh", "leg": n, "ok": age_h is not None and age_h <= s.opportunity_max_age_hours, "blocking": True,
                    "detail": "forecast age unknown" if age_h is None else f"the forecast is {age_h:.1f} hours old (limit {s.opportunity_max_age_hours:g})"})
        price = None if market is None else _side_price(market, leg.side)
        if price is None:
            reason = fresh.get("unavailable") or "no price on this side right now"
            out += [{"name": "price_ok", "leg": n, "ok": False, "blocking": True, "detail": reason},
                    {"name": "enough_contracts", "leg": n, "ok": False, "blocking": True, "detail": reason},
                    {"name": "still_worth_a_look", "leg": n, "ok": False, "blocking": False, "detail": reason}]
            continue
        drift = _dec(price) - leg.price
        out.append({"name": "price_ok", "leg": n, "ok": drift <= _dec(s.order_max_slippage_cents) / 100, "blocking": True,
                    "detail": f"the price now is {round(price * 100)}¢, prepared at {round(leg.price * 100)}¢ (limit: {s.order_max_slippage_cents:g}¢ worse)"})
        size = _side_size(market, leg.side)
        out.append({"name": "enough_contracts", "leg": n, "ok": size is not None and _dec(size) >= order.contracts, "blocking": True,
                    "detail": f"{'unknown' if size is None else f'{float(size):g}'} contracts offered at that price, {order.contracts} wanted"})
        out.append({"name": "still_worth_a_look", "leg": n, "ok": bool(market["meaningful"]), "blocking": False,
                    "detail": "the flag still holds" if market["meaningful"] else "the flag no longer holds"})
    return out


# ---- the steps ---------------------------------------------------------------------------------------------

async def prepare_ticket(app, user_id: int, contracts: int, legs_in: list[tuple[str, str]], now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    s = app.state.settings
    if contracts < 1 or contracts > s.order_max_contracts:
        raise OrderError(422, f"Contracts must be between 1 and {s.order_max_contracts}.")
    if not legs_in:
        raise OrderError(422, "A ticket needs at least one leg.")
    if len(legs_in) > s.ticket_max_legs:
        raise OrderError(422, f"A ticket may have at most {s.ticket_max_legs} legs.")
    if len({m for _, m in legs_in}) != len(legs_in):
        raise OrderError(422, "The same market is in the ticket twice.")
    fresh_all = [await fresh_market(app, leg) for leg in legs_in]
    prepared = []
    for (run_id, market_ticker), fresh in zip(legs_in, fresh_all):
        game, market = fresh["game"], fresh["market"]
        outcome = next((o for o in game["prediction"]["outcomes"] if o["market_ticker"] == market_ticker), None)
        if outcome is None:
            raise OrderError(404, "That market is not part of the forecast.")
        if fresh.get("unavailable") or market is None:
            raise OrderError(502, f"Today's prices could not be read: {fresh.get('unavailable') or 'no market'}")
        if market["side"] is None:
            raise OrderError(409, f"There is no price to buy at on {outcome['outcome']}.")
        if game["start"] is not None and game["start"] <= now:
            raise OrderError(409, f"The game has started ({game['title']}).")
        age_h = None if game["finished_at"] is None else (now - game["finished_at"]).total_seconds() / 3600
        if age_h is None or age_h > s.opportunity_max_age_hours:
            raise OrderError(409, f"The forecast for {game['title']} is too old (limit {s.opportunity_max_age_hours:g} hours). Research the game again.")
        side = market["side"]
        probability = outcome["probability"] if side == "yes" else 1 - outcome["probability"]
        prepared.append({"run_id": run_id, "market_ticker": market_ticker, "game": game, "outcome": outcome, "side": side,
                         "price": _dec(_side_price(market, side)), "probability": _dec(round(probability, 4)),
                         "multiplier": _dec((market.get("fee") or {}).get("multiplier", 1))})
    if len({p["game"]["event_ticker"] for p in prepared}) != len(prepared):
        raise OrderError(422, "Two legs are from the same game. Several markets of one game move together, so a ticket may hold one leg per game.")

    price = _combined([p["price"] for p in prepared])
    if price < CENT:
        raise OrderError(422, "The combined price is below one cent: the ticket is too unlikely to price.")
    probability = Decimal(1)
    for p in prepared:
        probability *= p["probability"]
    fee = fee_for_order(price, contracts, max(p["multiplier"] for p in prepared))  # the dearest leg's fee type: the cautious choice
    max_cost = price * contracts + fee
    gap = probability - price - fee / contracts
    first = prepared[0]
    single = len(prepared) == 1

    def create():
        with DbSession(app.state.engine) as db:
            order = Order(
                client_order_id=uuid.uuid4().hex, run_id=first["run_id"], event_ticker=first["game"]["event_ticker"], market_ticker=first["market_ticker"],
                outcome=first["outcome"]["outcome"] if single else " + ".join(p["outcome"]["outcome"] for p in prepared)[:500],
                title=first["game"]["title"] if single else f"Ticket of {len(prepared)} games"[:500],
                game_start=min((p["game"]["start"] for p in prepared if p["game"]["start"]), default=None),
                side=first["side"] if single else "yes", price=price, contracts=contracts, max_cost=max_cost, fee_estimate=fee,
                our_probability=probability.quantize(Decimal("0.0001")), gap=gap.quantize(Decimal("0.0001")),
                forecast_at=min((p["game"]["finished_at"] for p in prepared if p["game"]["finished_at"]), default=None),
                state="proposed", created_by=user_id, expires_at=now + timedelta(minutes=s.order_expiry_minutes),
            )
            if max_cost > _dec(s.order_max_cost_usd):
                raise OrderError(422, f"This ticket could cost ${max_cost:.2f}, above the limit of ${s.order_max_cost_usd:.2f} per order.")
            if day_cost(db, now) + max_cost > _dec(s.order_max_day_cost_usd):
                raise OrderError(422, f"This ticket would take today's total above the limit of ${s.order_max_day_cost_usd:.2f}.")
            db.add(order)
            db.flush()
            try:
                for position, p in enumerate(prepared):
                    db.add(OrderLeg(order_id=order.id, position=position, run_id=p["run_id"], event_ticker=p["game"]["event_ticker"],
                                    market_ticker=p["market_ticker"], outcome=p["outcome"]["outcome"], title=p["game"]["title"],
                                    game_start=p["game"]["start"], side=p["side"], price=p["price"], our_probability=p["probability"],
                                    forecast_at=p["game"]["finished_at"], open=True))
                db.flush()
            except IntegrityError:
                db.rollback()
                existing = db.scalar(select(OrderLeg.order_id).where(OrderLeg.market_ticker.in_([p["market_ticker"] for p in prepared]), OrderLeg.open))
                raise OrderError(409, "There is already an open ticket with one of these markets.", {"order_id": existing}) from None
            _record(db, order.id, None, "proposed", user_id, f"prepared at {float(price):.4f} for {contracts} contracts, {len(prepared)} leg(s)")
            db.commit()
            return order_to_dict(order, _legs_of(db, order.id))

    return await asyncio.to_thread(create)


async def prepare_order(app, user_id: int, run_id: str, market_ticker: str, contracts: int, now: datetime | None = None) -> dict:
    """A ticket of one leg."""
    return await prepare_ticket(app, user_id, contracts, [(run_id, market_ticker)], now)


def _expire_due(engine, now: datetime) -> int:
    with DbSession(engine) as db:
        due = db.scalars(select(Order).where(Order.state.in_(OPEN_STATES), Order.expires_at <= now)).all()
        count = 0
        for o in due:
            changed = db.execute(update(Order).where(Order.id == o.id, Order.state == o.state).values(state="expired")).rowcount
            if changed:
                _close_legs(db, o.id)
                _record(db, o.id, o.state, "expired", None, "not placed before it expired")
                count += 1
        db.commit()
        return count


async def expire_due(app, now: datetime | None = None) -> int:
    return await asyncio.to_thread(_expire_due, app.state.engine, now or datetime.now(UTC))


async def _checked(app, order_id: int, now: datetime):
    def load():
        with DbSession(app.state.engine) as db:
            order = db.get(Order, order_id)
            if order is None:
                raise OrderError(404, "Order not found.")
            legs = _legs_of(db, order_id)
            db.expunge_all()
            return order, legs

    order, legs = await asyncio.to_thread(load)
    fresh_all = [await fresh_market(app, (g.run_id, g.market_ticker)) for g in legs]

    def run_checks():
        with DbSession(app.state.engine) as db:
            return checks_for(order, legs, fresh_all, app.state.settings, db, now)

    return order, legs, await asyncio.to_thread(run_checks), fresh_all


async def order_with_checks(app, order_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    order, legs, checks, _ = await _checked(app, order_id, now)
    return order_to_dict(order, legs) | {"checks": checks if order.state in OPEN_STATES else []}


def _failed(checks: list[dict]) -> list[str]:
    return [c["name"] if c["leg"] is None else f"{c['name']} (leg {c['leg'] + 1})" for c in checks if c["blocking"] and not c["ok"]]


async def approve_order(app, order_id: int, user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    await expire_due(app, now)
    order, _, checks, _ = await _checked(app, order_id, now)
    if order.state != "proposed":
        raise OrderError(409, f"This order is {order.state}; only a proposed order can be approved.")
    failed = _failed(checks)
    if failed:
        raise OrderError(409, "The order cannot be approved: " + ", ".join(failed), {"checks": checks})

    def change():
        with DbSession(app.state.engine) as db:
            changed = db.execute(update(Order).where(Order.id == order_id, Order.state == "proposed", Order.expires_at > now)
                                 .values(state="approved", approved_by=user_id, approved_at=now)).rowcount
            if not changed:
                raise OrderError(409, "The order changed or expired while it was being approved.")
            _record(db, order_id, "proposed", "approved", user_id, "approved by a person")
            db.commit()

    await asyncio.to_thread(change)
    return await order_with_checks(app, order_id, now)


async def reject_order(app, order_id: int, user_id: int, reason: str | None, now: datetime | None = None) -> dict:
    def change():
        with DbSession(app.state.engine) as db:
            order = db.get(Order, order_id)
            if order is None:
                raise OrderError(404, "Order not found.")
            before = order.state
            changed = db.execute(update(Order).where(Order.id == order_id, Order.state.in_(OPEN_STATES))
                                 .values(state="rejected", reason=(reason or "")[:300] or None)).rowcount
            if not changed:
                raise OrderError(409, f"This order is {before}; only an open order can be rejected.")
            _close_legs(db, order_id)
            _record(db, order_id, before, "rejected", user_id, (reason or "rejected by a person")[:300])
            db.commit()
            db.refresh(order)
            return order_to_dict(order, _legs_of(db, order_id))

    return await asyncio.to_thread(change)


async def place_order(app, order_id: int, user_id: int, now: datetime | None = None) -> dict:
    """The separate step after approval: reads every leg's price once more, re-checks everything and records a simulated fill."""
    now = now or datetime.now(UTC)
    order, legs, checks, fresh_all = await _checked(app, order_id, now)
    if order.state != "approved":
        raise OrderError(409, f"This order is {order.state}; only an approved order can be placed.")
    failed = _failed(checks)
    leg_fills: dict[int, Decimal] = {}
    if failed:
        target = {"state": "expired", "reason": "not placed before it expired"} if failed == ["not_expired"] else {
            "state": "simulated_rejected", "reason": "checks failed at placing: " + ", ".join(failed)}
        values, detail = target, target["reason"]
    else:
        for leg, fresh in zip(legs, fresh_all):
            leg_fills[leg.position] = _dec(_side_price(fresh["market"], leg.side))
        price = _combined(list(leg_fills.values()))
        multiplier = max(_dec((f["market"].get("fee") or {}).get("multiplier", 1)) for f in fresh_all)
        fee = fee_for_order(price, order.contracts, multiplier)
        values = {"state": "placed", "placed_at": now, "fill_contracts": Decimal(order.contracts), "fill_price": price, "fill_fee": fee}
        detail = f"simulated fill of {order.contracts} contracts at {float(price):.4f}" + (f" ({len(legs)} legs)" if len(legs) > 1 else "")

    def change():
        with DbSession(app.state.engine) as db:
            changed = db.execute(update(Order).where(Order.id == order_id, Order.state == "approved").values(**values)).rowcount
            if not changed:  # someone else placed, rejected or expired it first: exactly one caller wins
                raise OrderError(409, "The order was already placed or changed.")
            _close_legs(db, order_id)
            for position, fill in leg_fills.items():
                db.execute(update(OrderLeg).where(OrderLeg.order_id == order_id, OrderLeg.position == position).values(fill_price=fill))
            _record(db, order_id, "approved", values["state"], user_id, detail)
            db.commit()
            return order_to_dict(db.get(Order, order_id), _legs_of(db, order_id))

    return await asyncio.to_thread(change)


def settle_orders(engine, now: datetime | None = None) -> int:
    """Settles placed tickets from the results that `resolve-records` fills in. A ticket is lost as soon as one leg has lost,
    won when every leg has won, and returned (paper result 0) when a leg was voided; otherwise it waits."""
    now = now or datetime.now(UTC)
    settled = 0
    with DbSession(engine) as db:
        for order in db.scalars(select(Order).where(Order.state == "placed")).all():
            legs = _legs_of(db, order.id)
            results: list[bool | None | str] = []
            for leg in legs:
                record = db.scalars(select(OutcomeRecord).where(
                    OutcomeRecord.market_ticker == leg.market_ticker, OutcomeRecord.resolved_at.is_not(None)
                ).order_by(OutcomeRecord.resolved_at.desc())).first()
                if record is None:
                    results.append(None)  # not known yet
                elif record.resolved_yes is None:
                    results.append("void")
                else:
                    won_leg = record.resolved_yes if leg.side == "yes" else not record.resolved_yes
                    leg.won = won_leg
                    results.append(won_leg)
            filled = order.fill_contracts or Decimal(0)
            if "void" in results:
                won, result, why = None, Decimal(0), "a leg was voided, so the stake is returned"
            elif False in results:
                won, result, why = False, -(order.fill_price or 0) * filled - (order.fill_fee or 0), "a leg lost"
            elif None in results:
                continue  # some legs are still unknown and none has lost
            else:
                won, result, why = True, filled - (order.fill_price or 0) * filled - (order.fill_fee or 0), "every leg won"
            changed = db.execute(update(Order).where(Order.id == order.id, Order.state == "placed")
                                 .values(state="settled", settled_at=now, won=won, paper_result=result)).rowcount
            if changed:
                _record(db, order.id, "placed", "settled", None, f"the game(s) ended; {why}")
                settled += 1
        db.commit()
    return settled


# ---- endpoints ---------------------------------------------------------------------------------------------

def _raise(exc: OrderError):
    raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail, **exc.extra}) from exc


class LegBody(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    market_ticker: str = Field(min_length=1, max_length=128)


class PrepareBody(BaseModel):
    contracts: int = Field(ge=1, le=1000)
    legs: list[LegBody] = Field(min_length=1, max_length=10)


class RejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


@router.post("", status_code=201, dependencies=[Depends(require_requested_with)])
async def prepare(body: PrepareBody, request: Request, user: Annotated[User, Depends(require_user)]):
    try:
        return await prepare_ticket(request.app, user.id, body.contracts, [(g.run_id, g.market_ticker) for g in body.legs])
    except OrderError as exc:
        _raise(exc)


@router.get("")
async def list_orders(request: Request, scope: Annotated[str, Query(pattern="^(open|recent|all)$")] = "recent", limit: Annotated[int, Query(ge=1, le=200)] = 50):
    await expire_due(request.app)

    def load():
        with DbSession(request.app.state.engine) as db:
            query = select(Order).order_by(Order.created_at.desc()).limit(limit)
            if scope == "open":
                query = query.where(Order.state.in_(OPEN_STATES))
            orders = [order_to_dict(o, _legs_of(db, o.id)) for o in db.scalars(query)]
            settled = [o for o in db.scalars(select(Order).where(Order.state == "settled"))]
            totals = {
                "settled": len(settled), "won": sum(1 for o in settled if o.won),
                "paper_result": float(sum((o.paper_result or 0) for o in settled)),
            }
            return {"orders": orders, "totals": totals}

    return await asyncio.to_thread(load)


@router.get("/{order_id}")
async def get_order(order_id: int, request: Request):
    await expire_due(request.app)
    try:
        return await order_with_checks(request.app, order_id)
    except OrderError as exc:
        _raise(exc)


@router.post("/{order_id}/approve", dependencies=[Depends(require_requested_with)])
async def approve(order_id: int, request: Request, user: Annotated[User, Depends(require_user)]):
    try:
        return await approve_order(request.app, order_id, user.id)
    except OrderError as exc:
        _raise(exc)


@router.post("/{order_id}/reject", dependencies=[Depends(require_requested_with)])
async def reject(order_id: int, body: RejectBody, request: Request, user: Annotated[User, Depends(require_user)]):
    try:
        return await reject_order(request.app, order_id, user.id, body.reason)
    except OrderError as exc:
        _raise(exc)


@router.post("/{order_id}/place", dependencies=[Depends(require_requested_with)])
async def place(order_id: int, request: Request, user: Annotated[User, Depends(require_user)]):
    try:
        return await place_order(request.app, order_id, user.id)
    except OrderError as exc:
        _raise(exc)
