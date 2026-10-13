"""The Opportunities page: what is worth a look right now.

It uses the forecasts we already have (the latest finished run of each game) and reads today's prices,
then runs the same comparison code as a run. No model call, no research: a few Kalshi reads. A forecast
older than OPPORTUNITY_MAX_AGE_HOURS is shown but never flagged: the facts it rests on may be out of date."""

import asyncio
import logging
import re
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session as DbSession

from app.auth import require_user
from app.config import Settings
from app.kalshi import KalshiClient
from app.models import OutcomeRecord, Run
from app.research.compare import compare_run

log = logging.getLogger("app.opportunities")

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"], dependencies=[Depends(require_user)])

MAX_GAMES = 50
CACHE_SECONDS = 60


def _event_of(market_ticker: str) -> str:
    """KXUCLTOTAL-26OCT13ATMMUN-1 belongs to the event KXUCLTOTAL-26OCT13ATMMUN."""
    return market_ticker.rsplit("-", 1)[0]


def _game_inputs(db: DbSession, run: Run) -> dict:
    """What the comparison needs from a stored run: its forecast, the plain-AI baseline and the market as it was."""
    records = db.scalars(select(OutcomeRecord).where(OutcomeRecord.run_id == run.id)).all()
    return {
        "run_id": run.id, "event_ticker": run.event_ticker, "title": run.event_title,
        "start": next((r.game_start for r in records if r.game_start), None),
        "finished_at": run.finished_at, "prediction": run.prediction,
        "baseline": {r.market_ticker: float(r.baseline_probability) for r in records if r.baseline_probability is not None},
        # the market as it was when the forecast was made, to see how far it has moved since
        "forecast_mids": {
            r.market_ticker: float((r.yes_bid + r.yes_ask) / 2)
            for r in records if r.yes_bid is not None and r.yes_ask is not None and 0 < r.yes_bid <= r.yes_ask < 1
        },
    }


def load_game(engine, run_id: str) -> dict | None:
    """One stored run with a forecast, started or not (the caller decides what that means), or None."""
    with DbSession(engine) as db:
        run = db.get(Run, run_id)
        if run is None or run.status != "done" or "outcomes" not in (run.prediction or {}):
            return None
        return _game_inputs(db, run)


def _load(engine, now: datetime) -> list[dict]:
    """The latest finished run with a prediction of each game that has not started, newest forecast first."""
    with DbSession(engine) as db:
        runs = db.scalars(
            select(Run).ext(distinct_on(Run.event_ticker)).where(Run.status == "done", Run.prediction.is_not(None))
            .order_by(Run.event_ticker, Run.created_at.desc())
        ).all()
        found = []
        for run in runs:
            if "outcomes" not in (run.prediction or {}):
                continue  # this game's latest run has no forecast
            game = _game_inputs(db, run)
            if game["start"] is not None and game["start"] <= now:
                continue  # started: nothing to bet on
            found.append(game)
    found.sort(key=lambda g: g["finished_at"] or now, reverse=True)
    return found[:MAX_GAMES]


async def evaluate_game(client: KalshiClient, settings: Settings, fee_cache: dict, game: dict) -> dict:
    """The fresh comparison of a stored game: today's prices, today's fees, the stored forecast."""
    events = {_event_of(o["market_ticker"]): None for o in game["prediction"]["outcomes"]}
    events.pop(game["event_ticker"], None)
    companions = [(event, event.split("-")[0]) for event in events]
    return await compare_run(client, game["event_ticker"], game["prediction"], settings, companions, game["baseline"], fee_cache)


def _normal(reason: str) -> str:
    return re.sub(r"[-+]?\d+(?:\.\d+)?", "#", reason)


def build_row(game: dict, comparison: dict, settings: Settings, now: datetime) -> dict:
    """One row for one game from its fresh comparison. The row shows the single best market."""
    prediction = game["prediction"]
    finished = game["finished_at"]
    age_hours = None if finished is None else max((now - finished).total_seconds() / 3600, 0)
    stale = age_hours is not None and age_hours > settings.opportunity_max_age_hours
    row = {
        "run_id": game["run_id"], "event_ticker": game["event_ticker"], "title": game["title"],
        "starts_at": game["start"].isoformat() if game["start"] else None,
        "forecast_at": finished.isoformat() if finished else None, "age_hours": None if age_hours is None else round(age_hours, 1),
        "stale": stale, "supported_claims": prediction.get("supported_claims", 0), "evidence": prediction.get("evidence"),
        "flagged": False, "flagged_markets": 0, "best": None, "unavailable": None, "risks": [],
    }
    if "unavailable" in comparison:
        row["unavailable"] = comparison["unavailable"]
        return row
    by_ticker = {o["market_ticker"]: o for o in prediction["outcomes"]}
    scored = [c for c in comparison["outcomes"] if c.get("net_edge") is not None]
    if not scored:
        row["unavailable"] = "No market had a price to compare with."
        return row
    flagged = [c for c in scored if c["meaningful"] and not stale]
    # In a two-outcome game "yes" on one side and "no" on the other are almost the same bet: count it once.
    winners = [t for t, o in by_ticker.items() if o.get("kind", "winner") == "winner"]
    if len(winners) == 2 and all(any(c["market_ticker"] == t for c in flagged) for t in winners):
        best_winner = max((c for c in flagged if c["market_ticker"] in winners), key=lambda c: c["net_edge"])
        flagged = [c for c in flagged if c["market_ticker"] not in winners or c is best_winner]
    pool = flagged or scored
    best = max(pool, key=lambda c: c["net_edge"])
    o = by_ticker[best["market_ticker"]]
    price = best["yes_ask"] if best["side"] == "yes" else best["no_ask"]
    ours = o["probability"] if best["side"] == "yes" else 1 - o["probability"]
    row.update(
        flagged=bool(flagged), flagged_markets=len(flagged),
        best={
            "market_ticker": best["market_ticker"], "kind": o.get("kind", "winner"), "market": o["outcome"], "side": best["side"],
            "price": price, "our_probability": round(ours, 4), "market_probability": price, "gap": best["net_edge"],
            "spread": o["spread"], "reasons": best["reasons"], "fee_source": (best.get("fee") or {}).get("source"),
        },
    )
    risks = list(best["reasons"]) if not flagged else []
    if stale:
        risks.insert(0, f"the forecast is {age_hours:.0f} hours old; the facts it rests on may be out of date")
    if (best.get("fee") or {}).get("source", "series") != "series":
        risks.append("the fee could not be read from Kalshi, so a standard fee was assumed")
    row["risks"] = risks
    return row


async def collect(engine, client: KalshiClient, settings: Settings, fee_cache: dict, now: datetime) -> list[tuple[dict, dict, dict]]:
    """For each game with a forecast that has not started: (stored game data, fresh comparison, row)."""
    games = await asyncio.to_thread(_load, engine, now)
    semaphore = asyncio.Semaphore(settings.sports_fetch_concurrency)

    async def one(game: dict) -> tuple[dict, dict, dict]:
        async with semaphore:
            comparison = await evaluate_game(client, settings, fee_cache, game)
        return game, comparison, build_row(game, comparison, settings, now)

    return list(await asyncio.gather(*(one(g) for g in games)))


async def build_opportunities(engine, client: KalshiClient, settings: Settings, fee_cache: dict, show_all: bool, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    rows = [row for _, _, row in await collect(engine, client, settings, fee_cache, now)]
    rows.sort(key=lambda r: (not r["flagged"], -(r["best"]["gap"] if r["best"] else -1)))
    shown = rows if show_all else [r for r in rows if r["flagged"]]
    reasons = Counter(_normal(x) for r in rows if not r["flagged"] and r["best"] for x in r["best"]["reasons"])
    return {
        "opportunities": shown, "games_considered": len(rows), "flagged_games": sum(1 for r in rows if r["flagged"]),
        "top_reasons": [{"reason": reason, "games": n} for reason, n in reasons.most_common(3)],
        "generated_at": now.isoformat(), "max_age_hours": settings.opportunity_max_age_hours, "max_ticket_legs": settings.ticket_max_legs,
    }


@router.get("")
async def opportunities(request: Request, all: Annotated[bool, Query()] = False):
    state = request.app.state
    cache = state.opportunity_cache
    entry = cache.get(all)
    if entry and time.monotonic() - entry[0] < CACHE_SECONDS:
        return entry[1]
    async with state.opportunity_lock:
        entry = cache.get(all)
        if entry and time.monotonic() - entry[0] < CACHE_SECONDS:
            return entry[1]
        result = await build_opportunities(state.engine, state.kalshi, state.settings, state.fee_cache, all)
        cache[all] = (time.monotonic(), result)
        return result
