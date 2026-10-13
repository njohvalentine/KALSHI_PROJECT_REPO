"""Runs one research run in the background and records the outcome in the database."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import Run
from app.research.pipeline import run_later_stages
from app.research.pricing import total_cost
from app.research.schemas import GameInfo, Usage
from app.research.sources import save_sources

log = logging.getLogger("app.research")


def summarize(state: dict, settings: Settings, extra_usages: dict[str, list[dict]] | None = None) -> dict:
    """Turns the final graph state (and the usages of the later stages) into the columns of the run record."""
    research = [Usage(**u) for u in state.get("usages", [])]
    groups = {"research": research} | {k: [Usage(**u) for u in v] for k, v in (extra_usages or {}).items()}
    usages = [u for group in groups.values() for u in group]
    cost, note = total_cost(usages)
    over_budget = cost is not None and float(cost) > settings.run_cost_warn_usd
    findings = state.get("findings", [])
    errors = state.get("errors", [])
    costs = {name: (None if (c := total_cost(group)[0]) is None else str(c)) for name, group in groups.items() if group}
    return {
        "plan": {"angles": state.get("angles", []), "cut_angles": state.get("cut_angles", 0)},
        "result": {"findings": findings, "errors": errors, "costs": costs},
        "input_tokens": sum(u.input_tokens for u in usages),
        "output_tokens": sum(u.output_tokens for u in usages),
        "search_calls": sum(u.search_calls for u in usages),
        "cost_usd": cost,
        "cost_note": note,
        "over_budget": over_budget,
        "status": "done" if findings else "failed",
        "error": None if findings else ("No researcher produced findings: " + "; ".join(
            f"{e['angle']}: {e['error']}" for e in errors))[:900] or "No researcher produced findings",
    }


def _update(engine, run_id: str, **fields) -> None:
    with DbSession(engine) as db:
        db.execute(update(Run).where(Run.id == run_id).values(**fields))
        db.commit()


def _save_research(engine, run_id: str, fields: dict, findings: list[dict], saved_at: datetime) -> None:
    """Research is done: keep its result and the cited pages now, and leave the run running for the later stages."""
    with DbSession(engine) as db:
        db.execute(update(Run).where(Run.id == run_id).values(
            plan=fields["plan"], result=fields["result"], stage="fetch", **{k: fields[k] for k in (
                "input_tokens", "output_tokens", "search_calls", "cost_usd", "cost_note", "over_budget")}))
        save_sources(db, run_id, findings, saved_at)  # commits


def _finish(engine, run_id: str, fields: dict, finished_at: datetime, prediction: dict | None) -> None:
    with DbSession(engine) as db:
        db.execute(update(Run).where(Run.id == run_id).values(finished_at=finished_at, stage="done", prediction=prediction, **fields))
        db.commit()


async def execute_run(
    *, engine, graph, settings: Settings, run_id: str, game: dict, judge=None, forecaster=None, kalshi=None,
    fetch_options: dict | None = None,
) -> None:
    await asyncio.to_thread(_update, engine, run_id, status="running", started_at=datetime.now(UTC), stage="research")
    config = {
        "configurable": {"thread_id": run_id},  # saved progress per run
        "max_concurrency": settings.max_researchers,
        "recursion_limit": 10,
        "tags": ["research"],
        "metadata": {"run_id": run_id, "event_ticker": game["event_ticker"]},
    }
    try:
        state = await graph.ainvoke({"game": game}, config)
        findings = state.get("findings", [])
        fields = summarize(state, settings)
        prediction = None
        if findings:
            await asyncio.to_thread(_save_research, engine, run_id, fields, findings, datetime.now(UTC))
            async def set_stage(name: str) -> None:
                await asyncio.to_thread(_update, engine, run_id, stage=name)

            later = await run_later_stages(
                engine=engine, run_id=run_id, game=GameInfo(**game), findings=findings, settings=settings, judge=judge,
                forecaster=forecaster, kalshi=kalshi, fetch_options=fetch_options, set_stage=set_stage,
            )
            prediction = later.prediction
            fields = summarize(state, settings, later.usages)
        if fields["over_budget"]:
            log.warning("Run %s cost %s USD, above RUN_COST_WARN_USD=%s", run_id, fields["cost_usd"], settings.run_cost_warn_usd)
        await asyncio.to_thread(_finish, engine, run_id, fields, datetime.now(UTC), prediction)
        log.info("Run %s %s (cost %s USD)", run_id, fields["status"], fields["cost_usd"])
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.to_thread(
            _update, engine, run_id, status="failed", error="Interrupted by a server shutdown",
            finished_at=datetime.now(UTC)))
        raise
    except Exception as exc:
        log.exception("Run %s failed", run_id)
        await asyncio.to_thread(
            _update, engine, run_id, status="failed",
            error=f"{type(exc).__name__} (details are in the server log)",
            finished_at=datetime.now(UTC))


def mark_stale_runs_failed(engine) -> int:
    """Runs still queued or running at startup were cut off by a restart: say so, visibly."""
    try:
        with DbSession(engine) as db:
            result = db.execute(
                update(Run).where(Run.status.in_(("queued", "running")))
                .values(status="failed", error="Interrupted by a restart", finished_at=datetime.now(UTC))
            )
            db.commit()
    except ProgrammingError as exc:
        raise RuntimeError(
            "The database tables are missing or out of date. Run the migrations first: alembic upgrade head"
        ) from exc
    if result.rowcount:
        log.warning("Marked %d unfinished run(s) as failed: interrupted by a restart", result.rowcount)
    return result.rowcount
