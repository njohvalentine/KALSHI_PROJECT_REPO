"""The Dashboard numbers: how our forecasts compare with the Kalshi price, from the same code as `score-records`.

The message at the top is written here, from the numbers, so it reads the same everywhere and cannot be more
optimistic than the scores allow."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.auth import require_user
from app.db import get_db
from app.models import Run
from app.research.records import MIN_GAMES, score_records

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(require_user)])

MIN_GAIN = 0.005  # the bar the replay plan used: a smaller difference counts as noise
MIN_SPORT_GAMES = 5
MIN_FLAGGED_BETS = 30


def verdict(games: int, ours: float | None, market: float | None) -> dict:
    """The sentence under the title. `gain` is Kalshi's score minus ours (lower scores are better, so positive means we are ahead)."""
    if games < MIN_GAMES or ours is None or market is None:
        return {"kind": "too_few", "text": f"Only {games} games have finished: too few to say anything yet."}
    gain = market - ours
    if gain >= MIN_GAIN:
        return {"kind": "ahead", "text": f"Our forecasts are ahead of the Kalshi price by {gain:.3f} on {games} games. This is not proof: look at each sport and keep scoring."}
    return {"kind": "no_edge", "text": f"No sign of an edge yet. On {games} finished games our forecasts are not better than the Kalshi price "
            f"(ours {ours:.3f}, Kalshi {market:.3f}). {games} games is not a final verdict."}


def build(score: dict, spend: dict) -> dict:
    same = score["same_records"]
    flagged = score["paper_flagged"]
    return {
        "games": score["games"],
        "outcomes": score["used"],
        "unresolved": score["excluded"]["unresolved"],
        "games_needed": MIN_GAMES,
        "message": verdict(score["games"], same["ours"], same["market"]),
        "scores": {"n": same["n"], "ours": same["ours"], "baseline": same["baseline"], "market": same["market"]},
        "by_sport": [
            {"sport": sport, "games": g["games"], "ours": g["same_records"]["ours"], "baseline": g["same_records"]["baseline"],
             "market": g["same_records"]["market"], "too_few": g["games"] < MIN_SPORT_GAMES}
            for sport, g in sorted(score["by_sport"].items(), key=lambda kv: -kv[1]["games"])
            if g["same_records"]["n"] > 0
        ],
        "chosen_side": score["paper_all"],
        "flagged": {**flagged, "too_few": flagged["bets"] < MIN_FLAGGED_BETS},
        "spend": spend,
    }


@router.get("")
def dashboard(request: Request, db: Annotated[DbSession, Depends(get_db)]):
    s = request.app.state.settings
    series = {e.ticker: (e.sport, e.league) for e in s.sports_series}
    score = score_records(request.app.state.engine, None, series, s.min_supported_claims)
    total, runs = db.execute(select(func.coalesce(func.sum(Run.cost_usd), 0), func.count()).where(Run.status == "done", Run.cost_usd.is_not(None))).one()
    window = db.scalar(select(func.count()).select_from(Run).where(Run.created_at >= datetime.now(UTC) - timedelta(hours=24))) or 0
    return build(score, {"total_usd": float(total), "runs": runs, "last_24h": window, "limit": s.research_max_per_day,
                         "note": "Calculated by the app from the tokens used and the prices it stores; it is not the OpenAI bill."})
