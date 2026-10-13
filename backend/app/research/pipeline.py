"""The stages after research: fetch the cited pages, check the claims, forecast, compare with the
market, and save the early records.

Each stage saves its own result in the database. A stage that fails does not turn into a quiet
default: the run's prediction says which stage failed and why, and the research stays available."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import ClaimCheck
from app.research.check import ClaimJudge, check_run, supported_claims
from app.research.compare import compare_run
from app.research.fetch import fetch_run_sources
from app.research.forecast import ForecastModel, run_baseline, run_forecasters, save_forecasts
from app.research.predict import build_prediction
from app.research.records import build_records, save_records
from app.research.schemas import GameInfo

log = logging.getLogger("app.research.pipeline")

NOT_CONFIGURED = "Checking and forecasting are not configured."
SWITCHED_OFF = "Source checking is switched off (FETCH_ENABLED, CHECK_ENABLED)."


@dataclass
class PipelineResult:
    prediction: dict
    usages: dict[str, list[dict]] = field(default_factory=lambda: {"check": [], "forecast": [], "baseline": []})


class StageFailed(Exception):
    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage} failed: {reason}")
        self.stage, self.reason = stage, reason


async def _stage(name: str, set_stage: Callable[[str], Awaitable[None]], work):
    await set_stage(name)
    try:
        return await work
    except Exception as exc:  # recorded in the run, logged in full; never a silent default
        log.exception("Stage %s failed", name)
        # Only the kind of error goes into the run (and so to the browser): the message can hold
        # database text, paths or fragments of a key. The full text is in the server log above.
        raise StageFailed(name, type(exc).__name__) from exc


def _supported(engine, run_id: str, findings: list[dict]) -> list[dict]:
    with DbSession(engine) as db:
        checks = db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == run_id)).all()
    return supported_claims(findings, checks)


async def run_later_stages(
    *, engine, run_id: str, game: GameInfo, findings: list[dict], settings: Settings, judge: ClaimJudge | None,
    forecaster: ForecastModel | None, kalshi, set_stage: Callable[[str], Awaitable[None]], fetch_options: dict | None = None,
) -> PipelineResult:
    result = PipelineResult(prediction={})
    if not (settings.fetch_enabled and settings.check_enabled):
        result.prediction = {"unavailable": SWITCHED_OFF}
        return result
    if judge is None or forecaster is None:
        result.prediction = {"unavailable": NOT_CONFIGURED}
        return result
    try:
        fetched = await _stage("fetch", set_stage, asyncio.to_thread(fetch_run_sources, engine, run_id, settings, **(fetch_options or {})))
        summary = await _stage("check", set_stage, check_run(engine, run_id, judge, settings))
        result.usages["check"] = summary.usages
        claims = _supported(engine, run_id, findings)

        async def forecast_all():
            async def no_baseline():
                return None, None

            # the forecasters and the plain-AI baseline run at the same time
            return await asyncio.gather(
                run_forecasters(game, claims, forecaster, settings),
                run_baseline(game, forecaster) if settings.record_baseline else no_baseline(),
            )

        forecast_set, (baseline, baseline_usage) = await _stage("forecast", set_stage, forecast_all())
        result.usages["forecast"] = forecast_set.usages
        result.usages["baseline"] = [baseline_usage] if baseline_usage else []
        prediction = build_prediction(game, forecast_set, len(claims))
        prediction["pipeline"] = {"pages": fetched, "claim_checks": summary.counts, "baseline": baseline is not None}
        if forecast_set.ok:
            await asyncio.to_thread(save_forecasts, engine, run_id, forecast_set)
            prediction["comparison"] = await _stage("compare", set_stage, compare_run(kalshi, game.event_ticker, prediction, settings))
            records = build_records(run_id, game, prediction, prediction["comparison"], baseline, datetime.now(UTC))
            await asyncio.to_thread(save_records, engine, records)
        result.prediction = prediction
    except StageFailed as failed:
        result.prediction = {"unavailable": str(failed)}
    return result
