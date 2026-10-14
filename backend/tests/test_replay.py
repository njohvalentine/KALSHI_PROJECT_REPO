"""The replay of the forecasting step on saved evidence. Fakes only: no model, no Kalshi, nothing written back."""

import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app import cli
from app.models import ClaimCheck, Forecast, OutcomeRecord, Run
from app.research.forecast import ForecastAnswer, OutcomeProbability
from app.research.records import save_records
from app.research.replay import estimate, format_summary, judge, load_candidates, replay, split_test_set, summarize
from app.research.schemas import Usage
from tests.conftest import alembic_config, needs_db
from tests.test_records import BASE, GAME, NOW, S, comparison, make_records, prediction

pytestmark = needs_db
CLAIM = {"kind": "sourced", "text": "A won 4 of the last 5.", "sources": [{"url": "https://example.test/form"}]}
UNCHECKED = {"kind": "sourced", "text": "A has a new coach.", "sources": [{"url": "https://example.test/coach"}]}


class FakeForecaster:
    """Gives every forecaster the same answer and remembers what it was shown."""

    def __init__(self, a=0.7, b=0.3, day=None):
        self.answer, self.day, self.seen = (a, b), day, []

    async def forecast(self, game, claims, framing):
        self.seen.append((game.event_ticker, [c["text"] for c in claims], self.day))
        return ForecastAnswer(probabilities=[OutcomeProbability(outcome_number=i, probability=p) for i, p in enumerate(self.answer, 1)], reasoning="x"), Usage("gpt-5.4", 3000, 0, 1500)


def seed(engine, run_id="run1", ticker="KX-1", created_at=NOW, a_wins=True):
    """A finished game: the run with its findings and one supported claim, the records with prices and the result."""
    pred = prediction() | {"comparison": comparison()}
    with DbSession(engine) as db:
        db.add(Run(id=run_id, event_ticker=ticker, event_title="A vs B", status="done", prediction=pred, created_at=created_at, finished_at=created_at,
                   result={"findings": [{"kind": "evidence", "angle": "Form", "claims": [CLAIM, UNCHECKED]}]}))
        db.add(ClaimCheck(run_id=run_id, finding_index=0, claim_index=0, source_url="https://example.test/form", verdict="supported", reason="r", model="m"))
        db.add(ClaimCheck(run_id=run_id, finding_index=0, claim_index=1, source_url="https://example.test/coach", verdict="could_not_check", reason="r", model="m"))
        db.commit()
    records = make_records(created_at=created_at, baseline={"KX-A": 0.5, "KX-B": 0.5}, starts_at=(created_at + timedelta(hours=4)).isoformat())
    for r in records:
        r.run_id, r.event_ticker = run_id, ticker
        r.resolved_at, r.resolved_yes = created_at + timedelta(hours=6), (r.market_ticker == "KX-A") == a_wins
    save_records(engine, records)


def counts(engine):
    with DbSession(engine) as db:
        return [db.scalar(select(func.count()).select_from(t)) for t in (Run, OutcomeRecord, ClaimCheck, Forecast)]


async def no_game(run_id):
    return None


def run_replay(engine, settings=S, items=None, rules_only=False, model=None, game=GAME):
    async def load(run_id):
        return asdict(game)

    model = model or FakeForecaster()
    items = items if items is not None else load_candidates(engine)
    return asyncio.run(replay(engine, settings, items, rules_only=rules_only, model_factory=lambda day: setattr(model, "day", day) or model, load_game=load)), model


def test_the_forecasters_get_the_saved_game_only_the_supported_claims_and_the_day_the_run_was_made(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    result, model = run_replay(fresh_db)
    assert result.games == 1 and len(model.seen) == S.forecaster_count
    assert model.seen[0] == ("KX-1", ["A won 4 of the last 5."], "2026-10-13")  # not "today", and the unchecked claim never went forward


def test_scores_of_the_replay_the_original_the_plain_ai_and_kalshi_on_the_same_outcomes(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    result, _ = run_replay(fresh_db, model=FakeForecaster(0.7, 0.3))
    s = summarize(result)["all"]
    assert (s["n"], s["games"]) == (2, 1)
    assert s["replay"] == pytest.approx(0.09)        # (0.3 ** 2 + 0.3 ** 2) / 2
    assert s["original"] == pytest.approx(0.1444)    # (0.38 ** 2) twice
    assert s["baseline"] == pytest.approx(0.25)
    assert s["market"] == pytest.approx(0.565 ** 2)  # mids 0.435 and 0.565
    assert summarize(result)["winner"]["n"] == 2


def test_the_flag_rule_replays_on_the_saved_prices_and_a_changed_limit_changes_the_flag(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    candidate = load_candidates(fresh_db)[0]
    now = judge(candidate.run.prediction, candidate.records, S)
    live = {o["market_ticker"]: o for o in comparison()["outcomes"]}
    for ticker, verdict in now.items():  # the same function, the same prices: the same verdict as the live comparison
        assert verdict["meaningful"] == live[ticker]["meaningful"] and verdict["side"] == live[ticker]["side"]
    assert any(v["meaningful"] for v in now.values())
    strict = judge(candidate.run.prediction, candidate.records, replace(S, edge_min=0.9))
    assert not any(v["meaningful"] for v in strict.values())


def test_rules_only_calls_no_model_and_pays_flagged_markets_by_the_result(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db, a_wins=True)
    result, model = run_replay(fresh_db, rules_only=True)
    assert model.seen == [] and result.usages == []
    s = summarize(result)
    # in a two-outcome game "yes" on A and "no" on B are the same bet at the same price (0.44): both are flagged and both won
    assert s["flags"]["flagged"] == 2 and s["flags"]["won"] == 2
    fee = 0.07 * 0.5 * 0.44 * 0.56
    assert s["flags"]["average_result"] == pytest.approx(1 - 0.44 - fee, abs=1e-6)
    assert s["original_flags"]["flagged"] == 2


def test_a_run_without_a_saved_game_is_skipped_and_counted_never_guessed(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    result = asyncio.run(replay(fresh_db, S, load_candidates(fresh_db), rules_only=False, model_factory=lambda d: FakeForecaster(), load_game=no_game))
    assert result.games == 0 and len(result.skipped) == 1 and "no saved game" in result.skipped[0]


def test_a_replay_changes_no_table(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    before = counts(fresh_db)
    run_replay(fresh_db)
    run_replay(fresh_db, rules_only=True)
    assert counts(fresh_db) == before


def test_later_games_are_held_back_as_the_test_set_and_final_shows_only_them(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db, "r1", "KX-1", NOW)
    seed(fresh_db, "r2", "KX-2", NOW + timedelta(days=1))
    seed(fresh_db, "r3", "KX-3", NOW + timedelta(days=2))
    items = load_candidates(fresh_db)
    cut = NOW + timedelta(hours=12)
    early, later = split_test_set(items, cut, False)
    assert [c.run.id for c in early] == ["r1"] and later == 2
    test, earlier = split_test_set(items, cut, True)
    assert [c.run.id for c in test] == ["r2", "r3"] and earlier == 1
    assert len(split_test_set(items, None, False)[0]) == 3
    assert [c.run.id for c in load_candidates(fresh_db, created_after=NOW + timedelta(hours=1))] == ["r2", "r3"]


def test_only_the_latest_run_of_a_game_with_a_result_is_used(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db, "old", "KX-1", NOW)
    seed(fresh_db, "new", "KX-1", NOW + timedelta(hours=1))
    assert [c.run.id for c in load_candidates(fresh_db)] == ["new"]


def test_a_game_with_no_result_yet_is_left_out(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    with DbSession(fresh_db) as db:
        for r in db.scalars(select(OutcomeRecord)):
            r.resolved_at = r.resolved_yes = None
        db.commit()
    assert load_candidates(fresh_db) == []


def test_the_estimate_and_the_report_say_what_it_costs_and_how_little_it_proves(fresh_db):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    items = load_candidates(fresh_db)
    calls, usd = estimate(items, S)
    assert calls == S.forecaster_count and usd == pytest.approx(calls * 0.035)
    result, _ = run_replay(fresh_db)
    report = format_summary(summarize(result), "all games")
    assert "Fewer than 30 games" in report and "not deterministic" in report and "Replay all games: 1 games, 2 outcomes." in report


def env(monkeypatch, fresh_db, key=True):
    for k, v in BASE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DATABASE_URL", fresh_db.plain_url)
    if key:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_the_command_prints_the_estimate_and_calls_nothing_without_yes(fresh_db, monkeypatch, capsys):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    env(monkeypatch, fresh_db)
    called = []
    monkeypatch.setattr("app.research.forecast.OpenAIForecastModel", lambda *a, **k: called.append(1))
    assert cli.main(["replay-forecasts", "--forecaster-count", "2"]) == 0
    out = capsys.readouterr().out
    assert "1 games x 2 forecasters = 2 model calls" in out and "Nothing was called" in out and called == []


def test_the_command_rules_only_needs_no_key_and_no_yes(fresh_db, monkeypatch, capsys):
    command.upgrade(alembic_config(), "head")
    seed(fresh_db)
    env(monkeypatch, fresh_db, key=False)
    assert cli.main(["replay-forecasts", "--rules-only", "--edge-min", "0.9", "--edge-plausible-max", "0.95"]) == 0
    out = capsys.readouterr().out
    assert "Replay all games (rules only): 1 games" in out and "Flagged by the rule in this replay: 0 markets" in out
    assert cli.main(["replay-forecasts"]) == 2  # with a model it needs the key


def test_the_command_refuses_final_without_a_cutoff_and_bad_values(fresh_db, monkeypatch, capsys):
    command.upgrade(alembic_config(), "head")
    env(monkeypatch, fresh_db)
    assert cli.main(["replay-forecasts", "--final"]) == 2 and "--final needs --tune-until" in capsys.readouterr().err
    assert cli.main(["replay-forecasts", "--tune-until", "yesterday"]) == 2
    assert cli.main(["replay-forecasts", "--edge-min", "lots"]) == 2
    assert cli.main(["replay-forecasts", "--rules-only"]) == 0 and "No finished game" in capsys.readouterr().out
