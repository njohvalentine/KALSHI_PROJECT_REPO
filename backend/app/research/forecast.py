"""Independent forecasters: each estimates a probability for every outcome of a game.

A forecaster sees the game, its outcomes and the checked (supported) claims only. It never sees a
price from the market, so the estimates can later be compared with the market honestly.

The answer is checked in code, not trusted: every outcome exactly once, no probability of exactly 0
or 1, and, where exactly one outcome happens (GameInfo.sums_to_one), the probabilities must add up
to about 100% (and are then scaled to exactly 100%). A forecast that fails is dropped, logged and
counted. With fewer than two valid forecasts there is no prediction, and the result says why."""

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import Forecast as ForecastRow
from app.research.model import ResearchModelError, _today, openai_client, usage_from
from app.research.prompts import EXCLUSIVE_RULE, FORECASTER_INSTRUCTIONS, FRAMINGS, GROUP_RULE, forecaster_input
from app.research.schemas import GameInfo, Usage

log = logging.getLogger("app.research.forecast")

MIN_VALID_FORECASTS = 2
SUM_TOLERANCE = 0.03


class OutcomeProbability(BaseModel):
    outcome_number: int
    probability: float


class ForecastAnswer(BaseModel):
    probabilities: list[OutcomeProbability]
    reasoning: str = Field(description="At most 120 words")


class InvalidForecast(Exception):
    """The forecaster's answer cannot be used. The message says why."""


class ForecastModel(Protocol):
    async def forecast(self, game: GameInfo, claims: list[dict], framing: tuple[str, str]) -> tuple[ForecastAnswer, Usage]: ...


class OpenAIForecastModel:
    def __init__(self, settings: Settings, client=None):
        self._s = settings
        self._client = client or openai_client(settings)

    async def forecast(self, game, claims, framing):
        today = _today()
        try:
            response = await self._client.responses.parse(
                model=self._s.forecaster_model,
                instructions=FORECASTER_INSTRUCTIONS.format(
                    today=today, framing=framing[1], exclusive_rule=EXCLUSIVE_RULE if game.sums_to_one else "",
                    group_rule=GROUP_RULE if game.groups else "",
                ),
                input=forecaster_input(game, claims, today),
                text_format=ForecastAnswer,
                reasoning={"effort": self._s.forecaster_reasoning_effort},
                max_output_tokens=self._s.forecaster_max_output_tokens,
                store=False,
            )
        except Exception as exc:
            raise ResearchModelError(f"Forecaster call failed: {type(exc).__name__}: {exc}") from exc
        if response.output_parsed is None:
            log.warning("The forecaster returned no usable answer: status %s, incomplete %s",
                        getattr(response, "status", None), getattr(response, "incomplete_details", None))
            raise ResearchModelError("The forecaster returned no usable answer")
        return response.output_parsed, usage_from(response, self._s.forecaster_model)


LINE_TOLERANCE = 0.03


def _clip(probs: dict[str, float], ticker: str, ceiling: float, what: str, notes: list[str]) -> None:
    """Lowers `ticker` to `ceiling` when it is higher by a small amount (and says so); a larger gap is an invalid answer."""
    excess = probs[ticker] - ceiling
    if excess <= 0:
        return
    if excess > LINE_TOLERANCE:
        raise InvalidForecast(f"{what} (by {excess:.2f})")
    notes.append(f"{what}: lowered by {excess:.3f}")
    probs[ticker] = ceiling


def enforce_consistency(game: GameInfo, probs: dict[str, float]) -> list[str]:
    """Probabilities of related markets must agree. Small disagreements are fixed by lowering the number that is
    too high (and reported); large ones raise InvalidForecast. Changes `probs` in place and returns the notes."""
    notes: list[str] = []
    winner = dict(zip(game.outcome_names, game.outcome_tickers))
    totals_15 = None
    for group in game.groups:
        lines: dict[str | None, list[tuple[float, str]]] = {}
        for ticker, strike, team in zip(group.tickers, group.strikes, group.teams):
            lines.setdefault(team, []).append((strike if strike is not None else 0.0, ticker))
        if group.kind in ("total", "spread"):
            for items in lines.values():
                items.sort()
                for (_, lower), (_, higher) in zip(items, items[1:]):  # a higher line is never more likely
                    _clip(probs, higher, probs[lower], f"{group.kind}: a higher line is more likely than a lower one", notes)
        if group.kind == "spread":
            for ticker, team in zip(group.tickers, group.teams):  # winning by more than 1.5 needs winning
                if team in winner:
                    _clip(probs, ticker, probs[winner[team]], "spread: winning by a margin is more likely than winning", notes)
        if group.kind == "total":
            totals_15 = next((t for t, strike in zip(group.tickers, group.strikes) if strike == 1.5), totals_15)
    if totals_15:
        for group in game.groups:
            if group.kind == "btts":
                for ticker in group.tickers:  # both teams scoring needs at least two goals
                    _clip(probs, ticker, probs[totals_15], "btts: both teams to score is more likely than over 1.5 goals", notes)
    return notes


def validate_full(game: GameInfo, answer: ForecastAnswer) -> tuple[dict[str, float], list[str]]:
    """Turns an answer into ({market ticker: probability}, adjustment notes) or raises InvalidForecast."""
    n = len(game.market_tickers)
    numbers = [p.outcome_number for p in answer.probabilities]
    if sorted(numbers) != list(range(1, n + 1)):
        raise InvalidForecast(f"expected one probability for each outcome 1..{n}, got outcome numbers {numbers}")
    probs = {p.outcome_number: p.probability for p in answer.probabilities}
    bad = [num for num, p in probs.items() if not 0 < p < 1]
    if bad:
        raise InvalidForecast(f"probability must be above 0 and below 1 (outcome numbers {bad})")
    winners = len(game.outcomes)
    if game.sums_to_one:  # only the winner outcomes add up to 100%
        total = sum(probs[i] for i in range(1, winners + 1))
        if abs(total - 1) > SUM_TOLERANCE:
            raise InvalidForecast(f"the outcomes are exclusive but the probabilities add up to {total:.3f}")
        for i in range(1, winners + 1):
            probs[i] = probs[i] / total
    by_ticker = {game.market_tickers[num - 1]: p for num, p in probs.items()}
    return by_ticker, enforce_consistency(game, by_ticker)


def validate(game: GameInfo, answer: ForecastAnswer) -> dict[str, float]:
    return validate_full(game, answer)[0]


@dataclass
class ValidForecast:
    index: int
    variant: str
    probabilities: dict[str, float]  # market ticker -> probability
    reasoning: str
    model: str
    adjustments: list[str] = field(default_factory=list)  # small inconsistencies that were fixed, in words


@dataclass
class ForecastSet:
    forecasts: list[ValidForecast] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)  # {index, variant, reason}
    usages: list[dict] = field(default_factory=list)
    evidence: str = "supported"  # "none" when no claim was supported

    @property
    def ok(self) -> bool:
        return len(self.forecasts) >= MIN_VALID_FORECASTS

    @property
    def unavailable_reason(self) -> str | None:
        if self.ok:
            return None
        why = "; ".join(f"forecaster {d['index'] + 1} ({d['variant']}): {d['reason']}" for d in self.dropped)
        return f"Only {len(self.forecasts)} valid forecast(s); at least {MIN_VALID_FORECASTS} are needed. {why}".strip()


async def run_forecasters(game: GameInfo, claims: list[dict], model: ForecastModel, settings: Settings) -> ForecastSet:
    if len(game.outcome_tickers) != len(game.outcomes) or not game.outcomes:
        raise ValueError("The game has no outcomes, or its outcome tickers do not match its outcomes")
    result = ForecastSet(evidence="supported" if claims else "none")

    async def one(index: int) -> None:
        framing = FRAMINGS[index % len(FRAMINGS)]
        try:
            answer, usage = await model.forecast(game, claims, framing)
        except Exception as exc:  # one failed forecaster must not lose the others; it is logged and counted
            log.warning("Forecaster %d (%s) failed: %s", index + 1, framing[0], exc)
            result.dropped.append({"index": index, "variant": framing[0], "reason": f"call failed: {type(exc).__name__}"})
            return
        result.usages.append(asdict(usage))  # the call was paid for even if its answer is unusable
        try:
            probabilities, adjustments = validate_full(game, answer)
        except InvalidForecast as exc:
            log.warning("Forecaster %d (%s) gave an unusable answer: %s", index + 1, framing[0], exc)
            result.dropped.append({"index": index, "variant": framing[0], "reason": str(exc)})
            return
        result.forecasts.append(ValidForecast(index, framing[0], probabilities, answer.reasoning.strip(), usage.model, adjustments))

    await asyncio.gather(*(one(i) for i in range(settings.forecaster_count)))
    result.forecasts.sort(key=lambda f: f.index)
    result.dropped.sort(key=lambda d: d["index"])
    if not result.ok:
        log.warning("No prediction for %s: %s", game.event_ticker, result.unavailable_reason)
    return result


def save_forecasts(engine, run_id: str, forecast_set: ForecastSet) -> int:
    """One row per forecaster and outcome."""
    rows = [
        ForecastRow(run_id=run_id, market_ticker=ticker, forecaster_index=f.index, variant=f.variant,
                    probability=round(p, 4), reasoning=f.reasoning[:2000], model=f.model)
        for f in forecast_set.forecasts for ticker, p in f.probabilities.items()
    ]
    with DbSession(engine) as db:
        db.add_all(rows)
        db.commit()
    return len(rows)


async def run_baseline(game: GameInfo, model: ForecastModel) -> tuple[dict[str, float] | None, dict | None]:
    """The plain-AI comparison: one forecaster call with no facts and no research. Returns
    (probabilities by market ticker, usage) or (None, usage or None) when the call or its answer failed;
    the failure is logged and never replaced by a guess."""
    framing = FRAMINGS[0]
    try:
        answer, usage = await model.forecast(game, [], framing)
    except Exception as exc:
        log.warning("The plain-AI baseline for %s failed: %s", game.event_ticker, exc)
        return None, None
    try:
        return validate(game, answer), asdict(usage)
    except InvalidForecast as exc:
        log.warning("The plain-AI baseline for %s was unusable: %s", game.event_ticker, exc)
        return None, asdict(usage)
