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
from app.models import Run, User
from app.research.runner import execute_run
from app.research.schemas import MarketInfo

log = logging.getLogger("app.runs")

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(require_user)])


def run_to_dict(run: Run, full: bool = True) -> dict:
    def iso(value: datetime | None):
        return value.isoformat() if value else None

    findings = (run.result or {}).get("findings", [])
    summary = {
        "id": run.id,
        "market_ticker": run.market_ticker,
        "market_title": run.market_title,
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
    }
    if full:
        summary["plan"] = run.plan
        summary["result"] = run.result
    return summary


class StartBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=128)


def _insert_run(engine, run_id: str, market: MarketInfo, user_id: int) -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        db.add(Run(id=run_id, market_ticker=market.ticker, market_title=market.title, status="queued", created_by=user_id))
        db.commit()


def _active_run_id(engine, ticker: str) -> str | None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        return db.scalar(select(Run.id).where(Run.market_ticker == ticker, Run.status.in_(("queued", "running"))))


async def _run_and_release(request_app, run_id: str, market: MarketInfo) -> None:
    state = request_app.state
    try:
        await execute_run(
            engine=state.engine, graph=state.research_graph, settings=state.settings,
            run_id=run_id, market=market.__dict__,
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
            raw = await run_in_threadpool(state.kalshi.get_market, body.ticker)
        except KalshiNotFound as exc:
            raise HTTPException(status_code=404, detail="Market not found") from exc
        except KalshiError as exc:
            raise HTTPException(status_code=502, detail=f"Kalshi request failed: {exc}") from exc
        try:
            market = MarketInfo.from_kalshi(raw)  # the server's copy of the market, not the browser's
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Kalshi returned market data we cannot use") from exc
        run_id = uuid.uuid4().hex
        try:
            await run_in_threadpool(_insert_run, state.engine, run_id, market, user.id)
        except IntegrityError:
            existing = await run_in_threadpool(_active_run_id, state.engine, market.ticker)
            return JSONResponse(
                status_code=409,
                content={"detail": "A run for this market is already in progress", "run_id": existing},
            )
        task = asyncio.create_task(_run_and_release(request.app, run_id, market))
        task_owns_slot = True  # _run_and_release gives the slot back when the run ends
        state.tasks.add(task)  # keep a reference so the task is not garbage collected
        task.add_done_callback(state.tasks.discard)
        return {"id": run_id, "status": "queued"}
    finally:
        if not task_owns_slot:
            state.active_runs -= 1


@router.get("/latest")
def latest_per_market(db: Annotated[DbSession, Depends(get_db)]):
    rows = db.scalars(
        select(Run).ext(distinct_on(Run.market_ticker)).order_by(Run.market_ticker, Run.created_at.desc())
    ).all()
    return {"runs": [{"market_ticker": r.market_ticker, "id": r.id, "status": r.status} for r in rows]}


@router.get("/{run_id}")
def get_run(run_id: str, db: Annotated[DbSession, Depends(get_db)]):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_to_dict(run)


@router.get("")
def list_runs(
    db: Annotated[DbSession, Depends(get_db)],
    ticker: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
):
    query = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if ticker:
        query = query.where(Run.market_ticker == ticker)
    return {"runs": [run_to_dict(r, full=False) for r in db.scalars(query)]}
