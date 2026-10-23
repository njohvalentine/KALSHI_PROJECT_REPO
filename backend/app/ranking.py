"""The ranked list of outcomes: every market of every researched game that has not started, on its more probable side, with the Kalshi price and the gap beside it.

It reuses what the Opportunities page already reads (the stored forecast of each game and today's prices, through `opportunities.collect`): no model call, no research,
a few Kalshi reads, a 60 second cache. A row is one market on the side our probability favours: our probability for that side, the range of the three forecasts, Kalshi's
ask for that side, the gap after fees (the same arithmetic as the run's comparison), the bookmakers' view for winner markets, the evidence, the risks in words and a
confidence level. The confidence level is a rule on how consistent the forecasts and the evidence are. It is not a chance of being right."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth import require_user
from app.config import Settings
from app.kalshi import KalshiClient
from app.measured import scored_games_by_sport
from app.models import OutcomeRecord
from app.opportunities import collect
from app.research.records import score_records

router = APIRouter(prefix="/api/ranking", tags=["ranking"], dependencies=[Depends(require_user)])

CACHE_SECONDS = 60
SPREAD_HIGH = 0.05  # the three forecasts agree within this many points for "high"
SPREAD_LOW = 0.10  # ... and disagree by more than this for "low"
FACTS_HIGH = 8  # supported facts needed for "high"
BOOK_DISAGREE = 0.10


def _points(x: float) -> int:
    return round(x * 100)


def confidence(*, stale: bool, supported: int, spread: float, tiers: dict | None, settings: Settings) -> dict:
    """{level: low|medium|high, reasons: [...]}. How consistent the three forecasts and the evidence are, not how likely the forecast is to be right."""
    low = []
    if stale:
        low.append(f"the forecast is older than {settings.opportunity_max_age_hours:g} hours")
    if supported == 0:
        low.append("no supported facts")
    elif supported < settings.min_supported_claims:
        low.append(f"only {supported} supported facts (fewer than {settings.min_supported_claims})")
    if spread > SPREAD_LOW:
        low.append(f"the three forecasts differ by {_points(spread)} points (more than {_points(SPREAD_LOW)})")
    if low:
        return {"level": "low", "reasons": low}
    official_or_news = None if not tiers else tiers.get("official", 0) + tiers.get("news", 0)
    medium = []
    if spread > SPREAD_HIGH:
        medium.append(f"the three forecasts differ by {_points(spread)} points (high needs {_points(SPREAD_HIGH)} or fewer)")
    if supported < FACTS_HIGH:
        medium.append(f"{supported} supported facts (high needs {FACTS_HIGH})")
    if official_or_news is None:
        medium.append("source kinds are not known (a forecast made before the labels existed)")
    elif official_or_news * 2 < supported:
        medium.append(f"only {official_or_news} of {supported} facts are from official or news sources (high needs half)")
    if medium:
        return {"level": "medium", "reasons": medium}
    return {"level": "high", "reasons": [f"the three forecasts agree within {_points(SPREAD_HIGH)} points", f"{supported} supported facts, {official_or_news} from official or news sources"]}


def rows_for_game(game: dict, comparison: dict, settings: Settings, now: datetime, scored: dict[str, int]) -> list[dict]:
    prediction = game["prediction"]
    finished = game["finished_at"]
    age_hours = None if finished is None else max((now - finished).total_seconds() / 3600, 0)
    stale = age_hours is not None and age_hours > settings.opportunity_max_age_hours
    supported = prediction.get("supported_claims", 0)
    tiers = prediction.get("source_tiers")
    measured = None if not game.get("sport") else scored.get(game["sport"], 0) >= settings.measured_min_games
    by_ticker = {c["market_ticker"]: c for c in comparison.get("outcomes", [])}
    unavailable = comparison.get("unavailable")
    rows = []
    for o in prediction["outcomes"]:
        p = o["probability"]
        side = "yes" if p >= 0.5 else "no"
        ours = p if side == "yes" else 1 - p
        low, high = (o["min"], o["max"]) if side == "yes" else (1 - o["max"], 1 - o["min"])
        comp = by_ticker.get(o["market_ticker"]) or {}
        side_info = comp.get(side)
        price = None if not side_info else side_info["price"]
        gap = None if not side_info else side_info["net_edge"]
        book = comp.get("book")
        book_p = None if not book else (book["probability"] if side == "yes" else 1 - book["probability"])
        flagged = bool(comp.get("meaningful") and comp.get("side") == side and not stale)
        risks: list[str] = []
        if stale:
            risks.append(f"the forecast is {age_hours:.0f} hours old; the facts it rests on may be out of date")
        if price is None:
            risks.append(unavailable or "no Kalshi price for this market right now")
        else:
            if abs(ours - price) >= settings.edge_plausible_max:
                risks.append(f"our probability differs from Kalshi's price by {_points(abs(ours - price))} points ({_points(settings.edge_plausible_max)} points or more: a model error is more likely than an opportunity)")
            if comp.get("side") == side:
                risks += [r for r in comp.get("reasons", []) if "model error" not in r]
        if book_p is not None and abs(ours - book_p) >= BOOK_DISAGREE:
            risks.append(f"the bookmakers see {_points(book_p)}% against our {_points(ours)}%")
        if o["spread"] > SPREAD_LOW:
            risks.append(f"the three forecasts differ by {_points(o['spread'])} points")
        if tiers and supported and tiers.get("other", 0) == supported:
            risks.append("all supported facts come from other sources (not an official site or a news outlet)")
        if measured is False:
            risks.append("this sport has no scored results yet, so nothing here has been tested")
        rows.append({
            "run_id": game["run_id"], "event_ticker": game["event_ticker"], "title": game["title"], "sport": game.get("sport"), "league": game.get("league"),
            "starts_at": game["start"].isoformat() if game["start"] else None, "forecast_at": finished.isoformat() if finished else None,
            "age_hours": None if age_hours is None else round(age_hours, 1), "market_ticker": o["market_ticker"], "kind": o.get("kind", "winner"), "market": o["outcome"],
            "side": side, "our_probability": round(ours, 4), "range": {"low": round(low, 4), "high": round(high, 4)}, "spread": o["spread"],
            "price": price, "gap": gap, "bookmaker_probability": None if book_p is None else round(book_p, 4), "bookmaker_count": None if not book else book.get("count"),
            "flagged": flagged, "supported_claims": supported, "source_tiers": tiers, "risks": risks,
            "confidence": confidence(stale=stale, supported=supported, spread=o["spread"], tiers=tiers, settings=settings),
        })
    return rows


async def build_ranking(engine, client: KalshiClient, settings: Settings, fee_cache: dict, now: datetime | None = None) -> dict:
    """Every row (unfiltered, most probable first), the accuracy so far, and how many games were considered."""
    now = now or datetime.now(UTC)
    games = await collect(engine, client, settings, fee_cache, now)
    scored = await asyncio.to_thread(scored_games_by_sport, engine)
    rows = [r for game, comparison, _ in games for r in rows_for_game(game, comparison, settings, now, scored)]
    rows.sort(key=lambda r: -r["our_probability"])
    series = {e.ticker: (e.sport, e.league) for e in settings.sports_series}
    score = await asyncio.to_thread(score_records, engine, None, series, settings.min_supported_claims)
    track = score.get("same_records") or {}
    return {"rows": rows, "games_considered": len(games), "generated_at": now.isoformat(), "max_age_hours": settings.opportunity_max_age_hours,
            "accuracy": {"games": score.get("games", 0), "ours": track.get("ours"), "kalshi": track.get("market")},
            "label_check": await asyncio.to_thread(confidence_vs_accuracy, engine, settings)}


def arrange(rows: list[dict], sort: str, hide_at: float, sport: str | None, kind: str | None, limit: int | None = None) -> list[dict]:
    """The order and the filters of the page. `hide_at`: outcomes whose price is at least this are left out (1.0 shows all)."""
    out = [r for r in rows if (sport is None or r["sport"] == sport) and (kind is None or r["kind"] == kind) and not (r["price"] is not None and r["price"] >= hide_at)]
    if sort == "gap":
        out.sort(key=lambda r: (r["gap"] is None, -(r["gap"] or 0)))
    else:
        out.sort(key=lambda r: -r["our_probability"])
    return out[:limit] if limit else out


def confidence_vs_accuracy(engine, settings: Settings) -> dict:
    """A descriptive check of the label on our own scored records: the Brier score of our probability, and of Kalshi's middle price, inside each label. The age of a forecast and the
    source kinds are not on a record, so a record can be "low" or "medium", never "high"; 'medium_or_high' is every record that is not low."""
    with DbSession(engine) as db:
        records = db.scalars(select(OutcomeRecord).where(OutcomeRecord.resolved_yes.is_not(None), OutcomeRecord.before_start.is_(True), OutcomeRecord.yes_bid.is_not(None),
                                                         OutcomeRecord.yes_ask.is_not(None), OutcomeRecord.prob_min.is_not(None))).all()
    latest: dict[str, OutcomeRecord] = {}
    for r in sorted(records, key=lambda r: (r.created_at, r.id)):
        latest[r.market_ticker] = r
    groups: dict[str, list[tuple[float, float, float]]] = {"low": [], "medium_or_high": []}
    for r in latest.values():
        level = confidence(stale=False, supported=r.supported_claims, spread=float(r.prob_max - r.prob_min), tiers=None, settings=settings)["level"]
        y = 1.0 if r.resolved_yes else 0.0
        groups["low" if level == "low" else "medium_or_high"].append((float(r.probability), float((r.yes_bid + r.yes_ask) / 2), y))
    return {name: {"n": len(v), "ours": sum((p - y) ** 2 for p, _, y in v) / len(v) if v else None, "kalshi": sum((m - y) ** 2 for _, m, y in v) / len(v) if v else None}
            for name, v in groups.items()}


@router.get("")
async def ranking(request: Request, sort: Annotated[str, Query(pattern="^(probability|gap)$")] = "probability", hide_at: Annotated[float, Query(gt=0, le=1)] = 0.95,
                  sport: Annotated[str | None, Query()] = None, kind: Annotated[str | None, Query()] = None, limit: Annotated[int | None, Query(ge=1, le=500)] = None):
    state = request.app.state
    entry = state.ranking_cache.get("all")
    if not (entry and time.monotonic() - entry[0] < CACHE_SECONDS):
        async with state.ranking_lock:
            entry = state.ranking_cache.get("all")
            if not (entry and time.monotonic() - entry[0] < CACHE_SECONDS):
                entry = (time.monotonic(), await build_ranking(state.engine, state.kalshi, state.settings, state.fee_cache))
                state.ranking_cache["all"] = entry
    data = entry[1]
    rows = arrange(data["rows"], sort, hide_at, sport, kind, limit)
    return {**{k: v for k, v in data.items() if k != "rows"}, "rows": rows, "total_rows": len(data["rows"]), "sports": sorted({r["sport"] for r in data["rows"] if r["sport"]}),
            "kinds": sorted({r["kind"] for r in data["rows"]})}
