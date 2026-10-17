"""Endpoints to start a research run and read its result. Login required."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.auth import require_requested_with, require_user
from app.db import get_db
from app.kalshi import KalshiError, KalshiNotFound
from app.measured import scored_games_in
from app.models import ClaimCheck, Forecast, OutcomeRecord, Run, SourcePage, User
from app.research.markets import attach_companions
from app.research.runner import execute_run
from dataclasses import asdict

from app.research.schemas import GameInfo

log = logging.getLogger("app.runs")

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_user)])


def _flagged(run: Run) -> int | None:
    outcomes = ((run.prediction or {}).get("comparison") or {}).get("outcomes")
    return None if outcomes is None else sum(1 for o in outcomes if o.get("meaningful"))


def run_to_dict(run: Run, full: bool = True, db: DbSession | None = None, measured_min_games: int | None = None) -> dict:
    def iso(value: datetime | None):
        return value.isoformat() if value else None

    findings = (run.result or {}).get("findings", [])
    summary = {
        "id": run.id,
        "event_ticker": run.event_ticker,
        "event_title": run.event_title,
        "status": run.status,
        "error": run.error,
        "created_at": iso(run.created_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "search_calls": run.search_calls,
        "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
        "cost_note": run.cost_note,
        "over_budget": run.over_budget,
        "sourced_claims": sum(1 for f in findings for c in f["claims"] if c["kind"] == "sourced"),
        "stage": run.stage,
        "flagged_outcomes": _flagged(run),
    }
    if full:
        summary["plan"] = run.plan
        summary["result"] = run.result
        summary["prediction"] = run.prediction
        summary["costs"] = (run.result or {}).get("costs")
        if db is not None:
            # Page text stays in the database: it is a copy of third-party pages and large.
            summary["pages"] = [
                {"url": p.url, "title": p.title, "fetch_status": p.fetch_status, "fetch_detail": p.fetch_detail,
                 "fetch_method": p.fetch_method, "http_status": p.http_status, "fetched_at": iso(p.fetched_at)}
                for p in db.scalars(select(SourcePage).where(SourcePage.run_id == run.id).order_by(SourcePage.id))
            ]
            summary["claim_checks"] = [
                {"finding_index": c.finding_index, "claim_index": c.claim_index, "source_url": c.source_url,
                 "verdict": c.verdict, "reason": c.reason}
                for c in db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == run.id).order_by(
                    ClaimCheck.finding_index, ClaimCheck.claim_index, ClaimCheck.source_url))
            ]
            baseline = {
                r.market_ticker: float(r.baseline_probability)
                for r in db.scalars(select(OutcomeRecord).where(OutcomeRecord.run_id == run.id))
                if r.baseline_probability is not None
            }
            summary["baseline"] = baseline or None  # the plain AI call with no research, per outcome
            sport = db.scalar(select(OutcomeRecord.sport).where(OutcomeRecord.run_id == run.id, OutcomeRecord.sport.is_not(None)).limit(1))
            summary["sport"] = sport
            # False when the sport has fewer scored games than MEASURED_MIN_GAMES (the flag has not been tested there); None when unknown
            summary["measured"] = None if not sport or measured_min_games is None else scored_games_in(db).get(sport, 0) >= measured_min_games
            summary["forecasts"] = [
                {"forecaster_index": f.forecaster_index, "variant": f.variant, "market_ticker": f.market_ticker,
                 "probability": float(f.probability), "reasoning": f.reasoning, "model": f.model}
                for f in db.scalars(select(Forecast).where(Forecast.run_id == run.id).order_by(
                    Forecast.forecaster_index, Forecast.market_ticker))
            ]
    return summary


class StartBody(BaseModel):
    event_ticker: str = Field(min_length=1, max_length=128)
    confirm_repeat: bool = False  # true: the person has seen that the game was researched recently and wants a new run


def _kickoff(kalshi, event_ticker: str) -> str | None:
    """The game's real start time from Kalshi's milestones, or None. The market's own occurrence time is
    the expected settlement time, so it is never a substitute: unknown is better than wrong."""
    try:
        data = kalshi.list_milestones(limit=5, related_event_ticker=event_ticker)
    except KalshiError as exc:
        log.warning("No start time for %s: %s", event_ticker, exc)
        return None
    for m in data.get("milestones", []):
        tickers = (m.get("primary_event_tickers") or []) + (m.get("related_event_tickers") or [])
        if event_ticker in tickers and m.get("start_date"):
            return m["start_date"]
    return None


class DailyLimitReached(Exception):
    """RESEARCH_MAX_PER_DAY runs were already made in the last 24 hours. `opens_at` is when the next slot opens."""

    def __init__(self, used: int, opens_at: datetime):
        super().__init__(f"{used} runs in the last 24 hours")
        self.used, self.opens_at = used, opens_at


LIMIT_LOCK = 7243001  # a fixed number for the database lock that makes "count, then insert" one step


def _insert_run(engine, run_id: str, game: GameInfo, user_id: int | None, trigger: str = "manual", limit: int = 0) -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        if limit:
            # One caller at a time counts and inserts, so two presses at once cannot both take the last slot.
            # The lock is released when this transaction ends.
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LIMIT_LOCK})
            made = db.scalars(select(Run.created_at).where(Run.created_at >= datetime.now(UTC) - timedelta(hours=24)).order_by(Run.created_at)).all()
            if len(made) >= limit:
                # the slot opens when enough of the oldest runs are 24 hours old that fewer than `limit` remain
                raise DailyLimitReached(len(made), made[len(made) - limit] + timedelta(hours=24))
        db.add(Run(id=run_id, event_ticker=game.event_ticker, event_title=game.title, status="queued", created_by=user_id, trigger=trigger))
        db.commit()


def _active_run_id(engine, event_ticker: str) -> str | None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        return db.scalar(select(Run.id).where(Run.event_ticker == event_ticker, Run.status.in_(("queued", "running"))))


async def _run_and_release(request_app, run_id: str, game: GameInfo) -> None:
    state = request_app.state
    try:
        await execute_run(
            engine=state.engine, graph=state.research_graph, settings=state.settings,
            run_id=run_id, game=asdict(game), judge=state.judge, forecaster=state.forecaster, kalshi=state.kalshi,
            fetch_options=state.fetch_options, odds=state.odds,
        )
    finally:
        state.active_runs -= 1


class RunStartError(Exception):
    """A run could not be started. `status_code` and `detail` are what the endpoint answers."""

    def __init__(self, status_code: int, detail: str, headers: dict | None = None, run_id: str | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.status_code, self.detail, self.headers, self.run_id, self.extra = status_code, detail, headers, run_id, extra


def _recent_run(engine, event_ticker: str, hours: float) -> tuple[float, Decimal | None] | None:
    """(hours ago, cost) of the latest finished run of the game whose forecast is still fresh, or None."""
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        run = db.scalar(select(Run).where(Run.event_ticker == event_ticker, Run.status == "done", Run.finished_at >= datetime.now(UTC) - timedelta(hours=hours))
                        .order_by(Run.finished_at.desc()).limit(1))
        return None if run is None else ((datetime.now(UTC) - run.finished_at).total_seconds() / 3600, run.cost_usd)


async def start_game_run(app, event_ticker: str, user_id: int | None, trigger: str = "manual", confirm_repeat: bool = False) -> dict:
    """Starts a run for a game in the background and returns {"id", "status"}. Used by the endpoint (a person
    pressed Research) and by the watcher (the automatic batch rule). Raises RunStartError."""
    state = app.state
    if state.research_graph is None:
        raise RunStartError(503, "Research is not configured. Set OPENAI_API_KEY and restart the backend.")
    if state.active_runs >= state.settings.max_concurrent_runs:
        raise RunStartError(429, "Too many runs in progress. Wait for one to finish.", headers={"Retry-After": "30"})
    if not confirm_repeat:
        # A fresh forecast exists: a new run costs the same again, so a person must say they want it. The watcher never does.
        recent = await run_in_threadpool(_recent_run, state.engine, event_ticker, state.settings.opportunity_max_age_hours)
        if recent is not None:
            hours, cost = recent
            ago = "less than an hour" if hours < 1 else f"{round(hours)} hours"
            price = "an unknown cost" if cost is None else f"${cost:.2f}"
            raise RunStartError(
                409,
                f"This game was researched {ago} ago for {price}, and its forecast is still fresh. A new run costs about the same and counts against "
                "today's limit. Prices may have moved, which you can see on the Opportunities page without a new run.",
                extra={"code": "recently_researched", "hours_ago": round(hours, 1), "cost_usd": None if cost is None else float(cost)},
            )
    state.active_runs += 1  # reserve the slot before any await, so parallel requests cannot overshoot
    task_owns_slot = False
    try:
        try:
            raw = await run_in_threadpool(state.kalshi.get_event, event_ticker)
        except KalshiNotFound as exc:
            raise RunStartError(404, "Game not found") from exc
        except KalshiError as exc:
            raise RunStartError(502, f"Kalshi request failed: {exc}") from exc
        try:
            starts_at = await run_in_threadpool(_kickoff, state.kalshi, event_ticker)
            game = GameInfo.from_kalshi_event(raw, starts_at=starts_at)  # the server's copy of the game
            series = (raw.get("event") or {}).get("series_ticker")
            entry = await run_in_threadpool(state.games.entry_of, series)
            sport = entry.sport if entry else None
            if not game.exclusive or len(game.outcomes) not in (2, 3):
                raise RunStartError(422, "This game has an unusual market structure (not two or three exclusive outcomes), so it cannot be researched yet.")
            game = GameInfo(**(game.__dict__ | {"sport": sport, "league": entry.league if entry else None}))
            game = await run_in_threadpool(attach_companions, game, raw, sport, state.kalshi)  # total, btts, spread if offered
        except ValueError as exc:
            raise RunStartError(502, "Kalshi returned game data we cannot use") from exc
        run_id = uuid.uuid4().hex
        try:
            await run_in_threadpool(_insert_run, state.engine, run_id, game, user_id, trigger, state.settings.research_max_per_day)
        except DailyLimitReached as limit:
            wait = max(int((limit.opens_at - datetime.now(UTC)).total_seconds()), 1)
            raise RunStartError(
                429,
                f"The daily research limit is reached: {limit.used} games in the last 24 hours. The next slot opens at {limit.opens_at:%H:%M} (UTC), "
                "when the oldest of them is 24 hours old. The limit is set by RESEARCH_MAX_PER_DAY.",
                headers={"Retry-After": str(wait)},
            ) from None
        except IntegrityError:
            existing = await run_in_threadpool(_active_run_id, state.engine, game.event_ticker)
            raise RunStartError(409, "A run for this game is already in progress", run_id=existing) from None
        task = asyncio.create_task(_run_and_release(app, run_id, game))
        task_owns_slot = True  # _run_and_release gives the slot back when the run ends
        state.tasks.add(task)  # keep a reference so the task is not garbage collected
        task.add_done_callback(state.tasks.discard)
        return {"id": run_id, "status": "queued"}
    finally:
        if not task_owns_slot:
            state.active_runs -= 1


@router.post("", status_code=202, dependencies=[Depends(require_requested_with)])
async def start_run(body: StartBody, request: Request, user: Annotated[User, Depends(require_user)]):
    try:
        return await start_game_run(request.app, body.event_ticker, user.id, confirm_repeat=body.confirm_repeat)
    except RunStartError as exc:
        if exc.status_code == 409:
            return JSONResponse(status_code=409, content={"detail": exc.detail, "run_id": exc.run_id, **(exc.extra or {})})
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=exc.headers) from exc


def _compact_forecast(run: Run) -> dict | None:
    """Our probability per outcome and whether it was flagged, for the Games list. No reasoning, no page text."""
    prediction = run.prediction or {}
    if run.status != "done" or "outcomes" not in prediction:
        return None
    comparison = prediction.get("comparison") or {}
    flagged = {o["market_ticker"]: bool(o.get("meaningful")) for o in comparison.get("outcomes", []) if "market_ticker" in o}
    return {
        "forecast_at": comparison.get("priced_at") or (run.finished_at.isoformat() if run.finished_at else None),
        "outcomes": [
            {"market_ticker": o["market_ticker"], "probability": o["probability"], "flagged": flagged.get(o["market_ticker"], False)}
            for o in prediction["outcomes"]
        ],
    }


@router.get("/latest")
def latest_per_game(db: Annotated[DbSession, Depends(get_db)]):
    rows = db.scalars(
        select(Run).ext(distinct_on(Run.event_ticker)).order_by(Run.event_ticker, Run.created_at.desc())
    ).all()
    return {"runs": [{"event_ticker": r.event_ticker, "id": r.id, "status": r.status, "forecast": _compact_forecast(r)} for r in rows]}


@router.get("/{run_id}")
def get_run(run_id: str, request: Request, db: Annotated[DbSession, Depends(get_db)]):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_to_dict(run, db=db, measured_min_games=request.app.state.settings.measured_min_games)


@router.get("")
def list_runs(
    db: Annotated[DbSession, Depends(get_db)],
    event_ticker: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
):
    query = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if event_ticker:
        query = query.where(Run.event_ticker == event_ticker)
    return {"runs": [run_to_dict(r, full=False) for r in db.scalars(query)]}
