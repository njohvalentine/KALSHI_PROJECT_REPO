"""Endpoints to start a research run and read its result. Login required."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.auth import require_requested_with, require_user
from app.db import get_db
from app.kalshi import KalshiError, KalshiNotFound
from app.models import ClaimCheck, Forecast, Run, SourcePage, User
from app.research.runner import execute_run
from dataclasses import asdict

from app.research.schemas import GameInfo

log = logging.getLogger("app.runs")

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_user)])


def _flagged(run: Run) -> int | None:
    outcomes = ((run.prediction or {}).get("comparison") or {}).get("outcomes")
    return None if outcomes is None else sum(1 for o in outcomes if o.get("meaningful"))


def run_to_dict(run: Run, full: bool = True, db: DbSession | None = None) -> dict:
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
            summary["forecasts"] = [
                {"forecaster_index": f.forecaster_index, "variant": f.variant, "market_ticker": f.market_ticker,
                 "probability": float(f.probability), "reasoning": f.reasoning, "model": f.model}
                for f in db.scalars(select(Forecast).where(Forecast.run_id == run.id).order_by(
                    Forecast.forecaster_index, Forecast.market_ticker))
            ]
    return summary


class StartBody(BaseModel):
    event_ticker: str = Field(min_length=1, max_length=128)


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


def _insert_run(engine, run_id: str, game: GameInfo, user_id: int) -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        db.add(Run(id=run_id, event_ticker=game.event_ticker, event_title=game.title, status="queued", created_by=user_id))
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
            fetch_options=state.fetch_options,
        )
    finally:
        state.active_runs -= 1


@router.post("", status_code=202, dependencies=[Depends(require_requested_with)])
async def start_run(body: StartBody, request: Request, user: Annotated[User, Depends(require_user)]):
    state = request.app.state
    if state.research_graph is None:
        raise HTTPException(status_code=503, detail="Research is not configured. Set OPENAI_API_KEY and restart the backend.")
    if state.active_runs >= state.settings.max_concurrent_runs:
        raise HTTPException(
            status_code=429, detail="Too many runs in progress. Wait for one to finish.", headers={"Retry-After": "30"}
        )
    state.active_runs += 1  # reserve the slot before any await, so parallel requests cannot overshoot
    task_owns_slot = False
    try:
        try:
            raw = await run_in_threadpool(state.kalshi.get_event, body.event_ticker)
        except KalshiNotFound as exc:
            raise HTTPException(status_code=404, detail="Game not found") from exc
        except KalshiError as exc:
            raise HTTPException(status_code=502, detail=f"Kalshi request failed: {exc}") from exc
        try:
            starts_at = await run_in_threadpool(_kickoff, state.kalshi, body.event_ticker)
            game = GameInfo.from_kalshi_event(raw, starts_at=starts_at)  # the server's copy of the game
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Kalshi returned game data we cannot use") from exc
        run_id = uuid.uuid4().hex
        try:
            await run_in_threadpool(_insert_run, state.engine, run_id, game, user.id)
        except IntegrityError:
            existing = await run_in_threadpool(_active_run_id, state.engine, game.event_ticker)
            return JSONResponse(
                status_code=409,
                content={"detail": "A run for this game is already in progress", "run_id": existing},
            )
        task = asyncio.create_task(_run_and_release(request.app, run_id, game))
        task_owns_slot = True  # _run_and_release gives the slot back when the run ends
        state.tasks.add(task)  # keep a reference so the task is not garbage collected
        task.add_done_callback(state.tasks.discard)
        return {"id": run_id, "status": "queued"}
    finally:
        if not task_owns_slot:
            state.active_runs -= 1


@router.get("/latest")
def latest_per_game(db: Annotated[DbSession, Depends(get_db)]):
    rows = db.scalars(
        select(Run).ext(distinct_on(Run.event_ticker)).order_by(Run.event_ticker, Run.created_at.desc())
    ).all()
    return {"runs": [{"event_ticker": r.event_ticker, "id": r.id, "status": r.status} for r in rows]}


@router.get("/{run_id}")
def get_run(run_id: str, db: Annotated[DbSession, Depends(get_db)]):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_to_dict(run, db=db)


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
