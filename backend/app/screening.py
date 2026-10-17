"""The free check before any research: do the bookmakers and Kalshi disagree enough on a game to be worth researching?

The rule is fixed and written down in docs/specs (FEAT-20261017-1127): a game is worth researching when, for a winner outcome and a
side, the bookmakers' consensus probability (margin removed) minus the Kalshi ask minus the fee is at least EDGE_MIN, at least
MIN_ASK_SIZE contracts are offered at that ask, and the game starts within SCREEN_HOURS_AHEAD hours. It uses no model and no OpenAI
credit. It reads the odds feed only when a person asks (one credit per league, through the same client and cache as a run), and it
refuses below SCREEN_MIN_CREDITS_LEFT credits so the monthly credits are not all spent here.

A game whose league has no bookmaker source, or that the feed does not list, is "cannot be screened", never promising and never
not promising. Every outcome checked is saved (table screenings) so the rule can be tested on real results later."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session as DbSession

from app.auth import require_user
from app.config import Settings
from app.models import Screening
from app.odds import OddsClient, OddsError, find_game, prices_by_ticker, sport_keys_for
from app.research.compare import ONE, FeeInfo, _series_fee, book_gap, fee_per_contract

log = logging.getLogger("app.screening")

router = APIRouter(prefix="/api/games", tags=["screening"], dependencies=[Depends(require_user)])


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def _usable(price: Decimal | None) -> Decimal | None:
    return price if price is not None and 0 < price < ONE else None


def _answer(status: str, text: str, best: dict | None = None) -> dict:
    return {"status": status, "text": text, "best": best}


def _sides(outcome: dict, fee: FeeInfo) -> tuple[dict | None, dict | None, Decimal | None, Decimal | None]:
    """The two sides of an outcome from the Games list prices: buy yes at the yes ask, buy no at one minus the yes bid."""
    bid, ask = _dec(outcome.get("bid")), _usable(_dec(outcome.get("ask")))
    no_ask = _usable(ONE - bid) if bid is not None else None
    yes = None if ask is None else {"price": ask, "fee": fee_per_contract(ask, fee), "size": _dec(outcome.get("ask_size"))}
    no = None if no_ask is None else {"price": no_ask, "fee": fee_per_contract(no_ask, fee), "size": _dec(outcome.get("bid_size"))}  # contracts at the best YES bid are those at the NO ask
    return yes, no, bid, ask


async def screen_games(games: list[dict], odds: OddsClient | None, kalshi, settings: Settings, fee_cache: dict, now: datetime) -> dict:
    """{results: {event ticker: {status, text, best}}, notes, credits: {remaining, used}, rows: [Screening]} for the games of the Games list."""
    out: dict = {"results": {}, "notes": [], "credits": None, "rows": []}
    if odds is None:
        out["notes"].append("The bookmaker feed is off (ODDS_ENABLED is not true), so games cannot be checked against the bookmakers.")
        return out
    try:
        active = await odds.active_sport_keys()  # free, and its answer carries the credits left
    except OddsError as exc:
        out["notes"].append(f"The odds feed could not be reached ({type(exc).__name__}); nothing was checked.")
        return out
    before = odds.credits_remaining
    if before is not None and before < settings.screen_min_credits_left:
        out["credits"] = {"remaining": before, "used": 0}
        out["notes"].append(f"Only {before} odds credits are left this month (SCREEN_MIN_CREDITS_LEFT is {settings.screen_min_credits_left}), so nothing was read. "
                            "The credits that remain are kept for the bookmaker price of researched games.")
        return out
    if before is None:
        out["notes"].append("The credits left could not be read, so the floor was not checked.")

    horizon = now + timedelta(hours=settings.screen_hours_ahead)
    by_key: dict[str, list[dict]] = {}
    for g in games:
        try:
            start = datetime.fromisoformat((g["starts_at"] or "").replace("Z", "+00:00"))
        except ValueError:
            out["results"][g["event_ticker"]] = _answer("cannot", "Cannot be screened: the start time is not known.")
            continue
        if start <= now or start > horizon:
            continue  # not checked: started, or too far ahead for a forecast made now to stay fresh
        if len(g["outcomes"]) not in (2, 3):
            out["results"][g["event_ticker"]] = _answer("cannot", "Cannot be screened: unusual market structure.")
            continue
        keys = sport_keys_for(g["event_ticker"].split("-")[0], active)
        if not keys:
            out["results"][g["event_ticker"]] = _answer("cannot", "Cannot be screened: no bookmaker source for this league.")
            continue
        for key in keys:
            by_key.setdefault(key, []).append(g)

    # the leagues with the most games first; the rest are left for another press
    ordered = sorted(by_key, key=lambda k: -len(by_key[k]))
    chosen, skipped = ordered[: settings.screen_max_leagues], ordered[settings.screen_max_leagues:]
    if skipped:
        out["notes"].append(f"{len(skipped)} league(s) were not read to save credits (SCREEN_MAX_LEAGUES is {settings.screen_max_leagues}).")

    settled: set[str] = set()  # games with a final answer; a game that can sit under several feed keys (tennis) is looked for under each
    tentative: dict[str, str] = {}  # why a game was not found so far
    for key in chosen:
        try:
            events = await odds.odds(key)
        except OddsError as exc:
            log.warning("Screening could not read %s: %s", key, exc)
            for g in by_key[key]:
                tentative[g["event_ticker"]] = f"the bookmaker prices could not be read ({type(exc).__name__})"
            continue
        read_at = datetime.now(UTC)
        for g in by_key[key]:
            ticker = g["event_ticker"]
            if ticker in settled:
                continue
            start = datetime.fromisoformat(g["starts_at"].replace("Z", "+00:00"))
            event, why = find_game(events, g["title"], start)
            if event is None:
                tentative[ticker] = why
                continue
            settled.add(ticker)
            prices = prices_by_ticker(event, [o["label"] for o in g["outcomes"]], [o["market_ticker"] for o in g["outcomes"]])
            if prices is None:
                out["results"][ticker] = _answer("cannot", "Cannot be screened: too few bookmakers priced every outcome, or an outcome name did not match.")
                continue
            fee = await _series_fee(kalshi, ticker.split("-")[0], ticker, fee_cache)
            best, rows = None, []
            for o in g["outcomes"]:
                yes, no, bid, ask = _sides(o, fee)
                gap = book_gap(prices[o["market_ticker"]], yes, no, None, settings, read_at.isoformat())
                rows.append(Screening(
                    created_at=read_at, event_ticker=ticker, market_ticker=o["market_ticker"], title=g["title"], outcome=o["label"],
                    sport=g.get("sport"), league=g.get("league"), game_start=start, yes_bid=bid, yes_ask=ask, no_ask=None if no is None else no["price"],
                    yes_ask_size=_dec(o.get("ask_size")), yes_bid_size=_dec(o.get("bid_size")), book_probability=Decimal(str(round(gap["probability"], 4))),
                    book_count=gap["count"], book_pinnacle=None if gap["pinnacle"] is None else Decimal(str(round(gap["pinnacle"], 4))),
                    side=gap["side"], net_edge=None if gap["edge"] is None else Decimal(str(round(gap["edge"], 4))),
                    enough_contracts=gap["enough_contracts"], passes=gap["passes"]))
                if gap["edge"] is not None and (best is None or gap["edge"] > best[1]["edge"]):
                    best = (o, gap, yes if gap["side"] == "yes" else no)
            out["rows"] += rows
            out["results"][ticker] = _verdict(best)
    chosen_games = {g["event_ticker"]: g for key in chosen for g in by_key[key]}
    for ticker in chosen_games:
        if ticker not in settled:
            out["results"][ticker] = _answer("cannot", f"Cannot be screened: {tentative.get(ticker, 'the bookmaker prices were not read')}.")
    every = {g["event_ticker"] for key in by_key for g in by_key[key]}
    for ticker in every - set(chosen_games):
        out["results"][ticker] = _answer("not_checked", f"Not checked: more than {settings.screen_max_leagues} leagues have games; press again to check others.")
    after = odds.credits_remaining
    out["credits"] = {"remaining": after, "used": None if before is None or after is None else max(before - after, 0)}
    return out


def _verdict(best) -> dict:
    if best is None:
        return _answer("cannot", "Cannot be screened: no Kalshi price to compare with.")
    outcome, gap, side = best
    cents = round(float(gap["edge"]) * 100)
    detail = {"market": outcome["label"], "side": gap["side"], "price": float(side["price"]), "book_probability": float(gap["probability"]),
              "book_count": gap["count"], "edge": float(gap["edge"]), "enough_contracts": gap["enough_contracts"]}
    if gap["passes"]:
        return _answer("promising", f"Worth researching: bookmakers put {outcome['label']} at {round(float(gap['probability']) * 100)}%, Kalshi sells “{gap['side']}” at "
                       f"{round(float(side['price']) * 100)}¢, gap {cents:+d}¢ after fees.", detail)
    why = " (too few contracts offered)" if gap["edge"] >= Decimal(0) and not gap["enough_contracts"] else ""
    return _answer("not_promising", f"Not promising: the best gap against the bookmakers is {cents:+d}¢ after fees{why}.", detail)


@router.get("/screen")
async def screen(
    request: Request,
    sport: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    more: bool = False,
):
    state = request.app.state
    data = await run_in_threadpool(state.games.query, sport, q, limit, False, more)
    result = await screen_games(data["games"], state.odds, state.kalshi, state.settings, state.fee_cache, datetime.now(UTC))
    rows = result.pop("rows")
    if rows:
        def save():
            with DbSession(state.engine) as db:
                db.add_all(rows)
                db.commit()
        await asyncio.to_thread(save)
    return result
