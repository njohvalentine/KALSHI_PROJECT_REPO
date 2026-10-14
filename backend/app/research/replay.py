"""Replay of the forecasting step on the evidence and prices saved before each game.

A fresh run on a finished game would let the live web search find the result. A replay cannot: the game the
forecasters saw (LangGraph checkpoint), the claims that went forward (findings and claim checks), the market of that
moment, the plain-AI call and the original forecast (outcome records) were all saved before the game. Nothing here is
written back: the replay is printed only. It produces candidates for settings; it does not replace new games."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import ClaimCheck, OutcomeRecord, Run
from app.research.check import supported_claims
from app.research.compare import FEE_RATE, FeeInfo, compare_outcome
from app.research.forecast import ForecastModel, run_forecasters
from app.research.predict import build_prediction
from app.research.pricing import total_cost
from app.research.records import _brier, _mid, _paper
from app.research.schemas import GameInfo, Usage

log = logging.getLogger("app.research.replay")

ESTIMATE_PER_CALL_USD = 0.035  # one forecaster of gpt-5.4 at medium effort: about 0.10 USD for three (measured 2026-10-13)
MIN_GAMES_NOTE = 30
CONCURRENT_GAMES = 2


@dataclass
class Candidate:
    run: Run
    records: list[OutcomeRecord]  # only the resolved ones


def load_candidates(engine, created_after: datetime | None = None, created_before: datetime | None = None) -> list[Candidate]:
    """The latest run of each game that has a forecast, records made before the start and results. A run with no
    resolved record is left out: there is nothing to score it against."""
    with DbSession(engine) as db:
        query = select(Run).where(Run.status == "done", Run.prediction.is_not(None)).order_by(Run.created_at)
        runs = [r for r in db.scalars(query) if "outcomes" in (r.prediction or {})]
        latest: dict[str, Run] = {}
        for r in runs:  # oldest first, so the last one wins
            latest[r.event_ticker] = r
        out = []
        for r in latest.values():
            if (created_after and r.created_at < created_after) or (created_before and r.created_at > created_before):
                continue
            records = [x for x in db.scalars(select(OutcomeRecord).where(OutcomeRecord.run_id == r.id))
                       if x.resolved_yes is not None and x.before_start is True]
            if records:
                db.expunge_all()
                out.append(Candidate(r, records))
        return sorted(out, key=lambda c: c.run.created_at)


def split_test_set(items: list[Candidate], tune_until: datetime | None, final: bool) -> tuple[list[Candidate], int]:
    """Without --tune-until everything is used. With it, only the games made up to that moment, and the later ones are
    counted and held back as the test set; --final then shows only that test set."""
    if tune_until is None:
        return items, 0
    early = [c for c in items if c.run.created_at <= tune_until]
    late = [c for c in items if c.run.created_at > tune_until]
    return (late, len(early)) if final else (early, len(late))


def _claims_of(engine, run: Run) -> list[dict]:
    with DbSession(engine) as db:
        checks = db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == run.id)).all()
    return supported_claims((run.result or {}).get("findings", []), checks)


def judge(prediction: dict, records: list[OutcomeRecord], settings: Settings) -> dict[str, dict]:
    """The flag rule on the prices saved with the records: the same function the live comparison uses."""
    by_ticker = {r.market_ticker: r for r in records}
    out = {}
    for o in prediction["outcomes"]:
        r = by_ticker.get(o["market_ticker"])
        if r is None:
            continue
        market = {
            "yes_bid_dollars": r.yes_bid, "yes_ask_dollars": r.yes_ask, "no_ask_dollars": r.no_ask,
            "yes_ask_size_fp": r.yes_ask_size, "yes_bid_size_fp": r.yes_bid_size,
        }
        fee = FeeInfo(r.fee_type or "quadratic", r.fee_multiplier if r.fee_multiplier is not None else Decimal(1), r.fee_source or "stored")
        out[o["market_ticker"]] = compare_outcome(
            o, market, fee, prediction["evidence"], prediction["supported_claims"], settings,
            None if r.baseline_probability is None else float(r.baseline_probability))
    return out


def _paper_of(rows: list[tuple[OutcomeRecord, dict]]) -> dict:
    """What buying the chosen side at the ask would have paid for the flagged markets of a replay."""
    results = []  # (won, paid per contract)
    for r, verdict in rows:
        if not verdict.get("meaningful"):
            continue
        side = verdict["side"]
        price = verdict[side]["price"]
        won = r.resolved_yes if side == "yes" else not r.resolved_yes
        fee = FEE_RATE * (r.fee_multiplier if r.fee_multiplier is not None else Decimal(1)) * price * (1 - price)
        results.append((won, (Decimal(1) if won else Decimal(0)) - price - fee))
    n = len(results)
    total = sum((x for _, x in results), Decimal(0))
    return {"flagged": n, "won": sum(1 for w, _ in results if w),
            "average_result": float(total / n) if n else None, "total_result": float(total) if n else None}


@dataclass
class ReplayResult:
    games: int = 0
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    held_back: int = 0
    held_back_is_early: bool = False
    rows: list[dict] = field(default_factory=list)  # per outcome: replay p, original p, baseline, kalshi mid, kind, result
    flag_rows: list[tuple[OutcomeRecord, dict]] = field(default_factory=list)
    original_records: list[OutcomeRecord] = field(default_factory=list)
    usages: list[Usage] = field(default_factory=list)


async def replay(
    engine, settings: Settings, items: list[Candidate], *, rules_only: bool, model_factory, load_game,
) -> ReplayResult:
    """`model_factory(date_string)` gives the forecaster model; `load_game(run_id)` gives the saved game (a dict) or None."""
    result = ReplayResult()
    gate = asyncio.Semaphore(CONCURRENT_GAMES)

    async def one(item: Candidate) -> None:
        run = item.run
        async with gate:
            if rules_only:
                prediction = run.prediction
            else:
                saved = await load_game(run.id)
                if saved is None:
                    result.skipped.append(f"{run.event_title}: no saved game (checkpoint) for this run")
                    return
                game = GameInfo(**saved)
                claims = await asyncio.to_thread(_claims_of, engine, run)
                forecast_set = await run_forecasters(game, claims, model_factory(run.created_at.date().isoformat()), settings)
                result.usages += [Usage(**u) for u in forecast_set.usages]
                if not forecast_set.ok:
                    result.failed.append(f"{run.event_title}: {forecast_set.unavailable_reason}")
                    return
                prediction = build_prediction(game, forecast_set, len(claims))
        verdicts = judge(prediction, item.records, settings)
        probs = {o["market_ticker"]: o["probability"] for o in prediction["outcomes"]}
        result.games += 1
        result.original_records += item.records
        for r in item.records:
            if r.market_ticker not in probs:
                continue
            result.rows.append({
                "event": r.event_ticker, "kind": r.market_kind, "new": probs[r.market_ticker], "old": r.probability, "yes": r.resolved_yes,
                "baseline": r.baseline_probability, "mid": _mid(r),
            })
            if r.market_ticker in verdicts:
                result.flag_rows.append((r, verdicts[r.market_ticker]))

    await asyncio.gather(*(one(i) for i in items))
    return result


def _b(rows: list[dict], key: str) -> float | None:
    return _brier([(Decimal(str(r[key])), r["yes"]) for r in rows])


def summarize(res: ReplayResult) -> dict:
    full = [r for r in res.rows if r["baseline"] is not None and r["mid"] is not None]
    winners = [r for r in full if r["kind"] == "winner"]

    def block(rows):
        return {"n": len(rows), "games": len({r["event"] for r in rows}),
                "replay": _b(rows, "new"), "original": _b(rows, "old"), "baseline": _b(rows, "baseline"), "market": _b(rows, "mid")}

    original_flagged = [r for r in res.original_records if r.meaningful]
    return {
        "games": res.games, "outcomes": len(res.rows), "all": block(full), "winner": block(winners),
        "flags": _paper_of(res.flag_rows), "original_flags": {**_paper(original_flagged), "flagged": len(original_flagged)},
        "skipped": res.skipped, "failed": res.failed, "held_back": res.held_back, "held_back_is_early": res.held_back_is_early,
        "cost": total_cost(res.usages), "calls": len(res.usages),
    }


def format_summary(s: dict, label: str) -> str:
    def f(x):
        return "n/a" if x is None else f"{x:.4f}"

    def line(name, b):
        return (f"{name}: {b['n']} outcomes in {b['games']} games. Brier (lower is better): replay {f(b['replay'])}, original forecast {f(b['original'])}, "
                f"plain AI {f(b['baseline'])}, Kalshi {f(b['market'])}")

    fl, of = s["flags"], s["original_flags"]
    lines = [
        f"Replay {label}: {s['games']} games, {s['outcomes']} outcomes.",
        line("  All markets that have a plain-AI call and a two-sided price", s["all"]),
        line("  Winner markets only", s["winner"]),
        f"  Flagged by the rule in this replay: {fl['flagged']} markets; buying the chosen side at the ask paid on average {f(fl['average_result'])} dollars per contract (total {f(fl['total_result'])}).",
        f"  Flagged when the runs were made (by the rule in force then, which changed during the first days): {of['flagged']} markets; average {f(of['average_result'])} dollars per contract (total {f(of['total_result'])}).",
    ]
    if s["calls"]:
        cost, note = s["cost"]
        lines.append(f"  Model calls: {s['calls']}, cost {'unknown' if cost is None else f'{cost:.2f} USD'}" + (f" ({note})" if note else "") + ".")
    if s["held_back"]:
        lines.append(f"  {s['held_back']} {'early' if s['held_back_is_early'] else 'later'} games are held back"
                     + ("." if s["held_back_is_early"] else " as the test set: run again with --final once the settings are fixed."))
    for kind in ("skipped", "failed"):
        for reason in s[kind]:
            lines.append(f"  {kind.capitalize()}: {reason}")
    lines.append("  Models are not deterministic: small differences between replays are noise. Tuning on few games fits noise; judge a change on games it was not tuned on.")
    if s["games"] < MIN_GAMES_NOTE:
        lines.append(f"  Fewer than {MIN_GAMES_NOTE} games: too few to conclude anything.")
    return "\n".join(lines)


def estimate(items: list[Candidate], settings: Settings) -> tuple[int, float]:
    calls = len(items) * settings.forecaster_count
    return calls, calls * ESTIMATE_PER_CALL_USD
