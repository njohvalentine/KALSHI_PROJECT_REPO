import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import cli
from app.config import load_settings
from app.kalshi import KalshiError
from app.models import OutcomeRecord
from app.research import records as rec
from app.research.compare import FeeInfo, compare
from app.research.forecast import ForecastAnswer, OutcomeProbability, run_baseline
from app.research.records import build_records, format_report, resolve_records, save_records, score_records
from app.research.schemas import GameInfo, Usage
from tests.conftest import alembic_config, needs_db

BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
S = load_settings(BASE | {"EDGE_PLAUSIBLE_MAX": "0.5"})
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
START = NOW + timedelta(hours=4)
GAME = GameInfo(event_ticker="KX-1", title="A vs B", starts_at=START.isoformat(), outcomes=["A wins", "B wins"],
                outcome_tickers=["KX-A", "KX-B"], exclusive=True)


def prediction():
    return {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [
        {"market_ticker": "KX-A", "outcome": "A wins", "probability": 0.62, "min": 0.58, "max": 0.66, "median_raw": 0.62, "spread": 0.08, "forecasts": []},
        {"market_ticker": "KX-B", "outcome": "B wins", "probability": 0.38, "min": 0.34, "max": 0.42, "median_raw": 0.38, "spread": 0.08, "forecasts": []}]}


EVENT = {"event": {"series_ticker": "KXT"}, "markets": [
    {"ticker": "KX-A", "yes_bid_dollars": "0.43", "yes_ask_dollars": "0.44", "yes_ask_size_fp": "120.50", "yes_bid_size_fp": "80"},
    {"ticker": "KX-B", "yes_bid_dollars": "0.56", "yes_ask_dollars": "0.57", "yes_ask_size_fp": "90", "yes_bid_size_fp": "60"}]}


def comparison():
    return compare(prediction(), EVENT, FeeInfo("quadratic_with_maker_fees", Decimal("0.5"), "series"), S, NOW, baseline={"KX-A": 0.50, "KX-B": 0.50})


def make_records(created_at=NOW, baseline=None, **game_kw):
    game = GameInfo(**(GAME.__dict__ | game_kw))
    return build_records("run1", game, prediction(), comparison(), baseline, created_at)


def test_one_record_per_outcome_with_the_forecast_the_market_and_the_rules_verdict():
    a, b = make_records(baseline={"KX-A": 0.55, "KX-B": 0.45})
    assert (a.market_ticker, a.outcome, a.probability, a.prob_min, a.prob_max) == ("KX-A", "A wins", Decimal("0.62"), Decimal("0.58"), Decimal("0.66"))
    assert (a.forecasters_valid, a.evidence, a.supported_claims, a.baseline_probability) == (3, "supported", 7, Decimal("0.55"))
    assert (a.yes_bid, a.yes_ask, a.no_ask, a.yes_ask_size) == (Decimal("0.43"), Decimal("0.44"), Decimal("0.57"), Decimal("120.5"))
    assert a.yes_bid_size == Decimal("80")  # contracts at the best YES bid are those at the NO ask
    assert (a.fee_type, a.fee_multiplier, a.fee_source, a.priced_at) == ("quadratic_with_maker_fees", Decimal("0.5"), "series", NOW)
    assert a.side == "yes" and a.net_edge > 0 and a.meaningful is True and a.reasons == []
    assert (a.run_id, a.event_ticker, a.game_start, a.created_at) == ("run1", "KX-1", START, NOW)
    assert b.baseline_probability == Decimal("0.45") and b.side == "no"


@pytest.mark.parametrize("created_at,start,expected", [
    (NOW, START, True), (START + timedelta(minutes=1), START, False), (NOW, None, None)])
def test_before_start_is_true_false_or_unknown(created_at, start, expected):
    records = make_records(created_at=created_at, starts_at=start.isoformat() if start else None)
    assert records[0].before_start is expected and records[0].game_start == start


def test_no_baseline_leaves_the_field_empty():
    assert make_records()[0].baseline_probability is None


def test_no_prediction_means_no_records():
    assert build_records("r", GAME, {"unavailable": "x", "forecasters_valid": 1, "dropped": [], "evidence": "supported", "supported_claims": 3},
                         {"unavailable": "x"}, None, NOW) == []


def test_unreadable_prices_still_record_the_forecast_and_say_why():
    records = build_records("r", GAME, prediction(), {"unavailable": "Kalshi prices could not be read: down"}, None, NOW)
    r = records[0]
    assert r.probability == Decimal("0.62") and r.yes_ask is None and r.side is None and r.meaningful is False
    assert r.reasons == ["no market snapshot: Kalshi prices could not be read: down"]


class FakeBaselineModel:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def forecast(self, game, claims, framing):
        self.calls.append((claims, framing[0]))
        if self.error:
            raise self.error
        return self.answer, Usage("gpt-5.4", 900, 0, 700)


def answer(a, b):
    return ForecastAnswer(probabilities=[OutcomeProbability(outcome_number=1, probability=a), OutcomeProbability(outcome_number=2, probability=b)], reasoning="x")


def test_the_baseline_is_one_call_with_no_facts_and_the_first_framing():
    model = FakeBaselineModel(answer(0.6, 0.4))
    probs, usage = asyncio.run(run_baseline(GAME, model))
    assert model.calls == [([], "evidence_first")] and probs == {"KX-A": 0.6, "KX-B": 0.4} and usage["input_tokens"] == 900


def test_a_failed_or_unusable_baseline_is_none_not_a_guess(caplog):
    probs, usage = asyncio.run(run_baseline(GAME, FakeBaselineModel(error=RuntimeError("boom"))))
    assert probs is None and usage is None and "baseline" in caplog.text
    probs, usage = asyncio.run(run_baseline(GAME, FakeBaselineModel(answer(0.9, 0.9))))  # adds up to 1.8
    assert probs is None and usage is not None  # the call was paid for


@needs_db
def test_records_are_saved_unique_per_run_and_outcome(fresh_db):
    command.upgrade(alembic_config(), "head")
    assert "outcome_records" in inspect(fresh_db).get_table_names()
    assert save_records(fresh_db, make_records()) == 2
    with pytest.raises(IntegrityError, match="uq_outcome_records_run_market"):
        save_records(fresh_db, make_records())
    with DbSession(fresh_db) as db:
        assert db.query(OutcomeRecord).count() == 2


class FakeKalshiMarkets:
    def __init__(self, markets, fail_on_call=None):
        self.markets, self.fail_on_call, self.calls = markets, fail_on_call, []

    def list_markets(self, **kw):
        self.calls.append(kw)
        if self.fail_on_call == len(self.calls):
            raise KalshiError("down")
        wanted = kw["tickers"].split(",")
        return {"markets": [m for m in self.markets if m["ticker"] in wanted]}


def finished(ticker, result, value, status="finalized"):
    return {"ticker": ticker, "status": status, "result": result, "settlement_value_dollars": value}


def stored(fresh_db, **kw):
    command.upgrade(alembic_config(), "head")
    save_records(fresh_db, make_records(**kw))


def fetch_all(fresh_db):
    with DbSession(fresh_db) as db:
        return {r.market_ticker: r for r in db.query(OutcomeRecord).all()}


LATER = START + timedelta(hours=4)  # past the 3 hours after the start


@needs_db
def test_resolve_fills_in_yes_no_and_leaves_open_and_missing_markets(fresh_db):
    stored(fresh_db)
    kalshi = FakeKalshiMarkets([finished("KX-A", "yes", "1.0000"), {"ticker": "KX-B", "status": "active", "result": "", "settlement_value_dollars": None}])
    assert resolve_records(fresh_db, kalshi, S, now=LATER) == {"resolved": 1, "voided_or_other": 0, "still_open": 1, "not_found": 0, "orders_settled": 0}
    rows = fetch_all(fresh_db)
    assert rows["KX-A"].resolved_yes is True and rows["KX-A"].settlement_value == Decimal("1.0000") and rows["KX-A"].resolved_at == LATER
    assert rows["KX-B"].resolved_at is None
    assert kalshi.calls == [{"tickers": "KX-A,KX-B", "limit": 2}]
    kalshi2 = FakeKalshiMarkets([finished("KX-B", "no", "0.0000")])
    assert resolve_records(fresh_db, kalshi2, S, now=LATER + timedelta(hours=1))["resolved"] == 1
    assert fetch_all(fresh_db)["KX-B"].resolved_yes is False
    assert resolve_records(fresh_db, FakeKalshiMarkets([]), S, now=LATER + timedelta(hours=2)) == {"resolved": 0, "voided_or_other": 0, "still_open": 0, "not_found": 0, "orders_settled": 0}


@needs_db
def test_voided_and_missing_markets_are_counted_and_not_given_a_winner(fresh_db):
    stored(fresh_db)
    kalshi = FakeKalshiMarkets([finished("KX-A", "scalar", "0.5000", status="determined")])  # settled at another value
    counts = resolve_records(fresh_db, kalshi, S, now=LATER)
    assert counts == {"resolved": 0, "voided_or_other": 1, "still_open": 0, "not_found": 1, "orders_settled": 0}
    row = fetch_all(fresh_db)["KX-A"]
    assert row.resolved_at == LATER and row.resolved_yes is None and row.settlement_value == Decimal("0.5000")


@needs_db
def test_games_that_started_less_than_the_wait_ago_are_not_asked_about(fresh_db):
    stored(fresh_db)
    kalshi = FakeKalshiMarkets([finished("KX-A", "yes", "1.0000")])
    assert resolve_records(fresh_db, kalshi, S, now=START + timedelta(hours=2)) == {"resolved": 0, "voided_or_other": 0, "still_open": 0, "not_found": 0, "orders_settled": 0}
    assert kalshi.calls == []


@needs_db
def test_records_without_a_start_time_are_asked_about_after_a_day(fresh_db):
    stored(fresh_db, starts_at=None)
    kalshi = FakeKalshiMarkets([finished("KX-A", "yes", "1.0000")])
    assert resolve_records(fresh_db, kalshi, S, now=NOW + timedelta(hours=23))["resolved"] == 0 and kalshi.calls == []
    assert resolve_records(fresh_db, kalshi, S, now=NOW + timedelta(hours=25))["resolved"] == 1


@needs_db
def test_only_the_result_fields_change_and_a_kalshi_failure_keeps_earlier_batches(fresh_db, monkeypatch):
    stored(fresh_db)
    before = {c.name: {t: getattr(r, c.name) for t, r in fetch_all(fresh_db).items()} for c in OutcomeRecord.__table__.columns}
    monkeypatch.setattr(rec, "BATCH", 1)  # one market per call, so the second call can fail after the first is saved
    kalshi = FakeKalshiMarkets([finished("KX-A", "yes", "1.0000"), finished("KX-B", "no", "0.0000")], fail_on_call=2)
    with pytest.raises(KalshiError):
        resolve_records(fresh_db, kalshi, S, now=LATER)
    after = {c.name: {t: getattr(r, c.name) for t, r in fetch_all(fresh_db).items()} for c in OutcomeRecord.__table__.columns}
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"resolved_at", "resolved_yes", "settlement_value"}
    rows = fetch_all(fresh_db)
    assert rows["KX-A"].resolved_yes is True and rows["KX-B"].resolved_at is None


def scored_record(event, p, yes, baseline, bid, ask, side, no_ask=None, meaningful=False, before=True, resolved=True, voided=False):
    return OutcomeRecord(
        run_id=f"run-{event}", event_ticker=event, market_ticker=f"{event}-M", outcome="x", game_start=START, created_at=NOW, before_start=before,
        probability=Decimal(str(p)), prob_min=Decimal(str(p)), prob_max=Decimal(str(p)), forecasters_valid=3, evidence="supported",
        supported_claims=7, baseline_probability=None if baseline is None else Decimal(str(baseline)),
        yes_bid=None if bid is None else Decimal(str(bid)), yes_ask=None if ask is None else Decimal(str(ask)),
        no_ask=None if no_ask is None else Decimal(str(no_ask)), fee_multiplier=Decimal(1), side=side, meaningful=meaningful,
        resolved_at=NOW if resolved else None, resolved_yes=None if (voided or not resolved) else yes,
    )


@needs_db
def test_scores_on_a_hand_worked_set(fresh_db):
    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        db.add_all([
            scored_record("E1", 0.8, True, 0.6, 0.50, 0.54, "yes", meaningful=True),
            scored_record("E2", 0.3, False, 0.5, 0.40, 0.44, "no", no_ask=0.60),
            scored_record("E3", 0.6, False, 0.7, 0.50, 0.55, "yes"),
            scored_record("E4", 0.5, True, 0.5, None, None, None),  # no two-sided quote
            scored_record("E5", 0.9, True, 0.5, 0.5, 0.6, "yes", resolved=False),   # not resolved
            scored_record("E6", 0.9, True, 0.5, 0.5, 0.6, "yes", voided=True),      # voided
            scored_record("E7", 0.9, True, 0.5, 0.5, 0.6, "yes", before=False),     # made after the start
            scored_record("E8", 0.9, True, 0.5, 0.5, 0.6, "yes", before=None),      # start unknown
        ])
        db.commit()
    s = score_records(fresh_db)
    assert (s["records"], s["used"], s["games"]) == (8, 4, 4)
    assert s["excluded"] == {"unresolved": 1, "voided_or_other": 1, "after_start_or_unknown": 2}
    assert s["brier_ours"] == pytest.approx(0.185)
    assert s["same_records"]["n"] == 3
    assert s["same_records"]["ours"] == pytest.approx((0.04 + 0.09 + 0.36) / 3)
    assert s["same_records"]["baseline"] == pytest.approx((0.16 + 0.25 + 0.49) / 3)
    assert s["same_records"]["market"] == pytest.approx((0.48 ** 2 + 0.42 ** 2 + 0.525 ** 2) / 3)
    assert s["without_two_sided_quote"] == 1 and s["without_baseline"] == 0
    won1, won2, lost3 = 1 - 0.54 - 0.07 * 0.54 * 0.46, 1 - 0.60 - 0.07 * 0.60 * 0.40, -0.55 - 0.07 * 0.55 * 0.45
    assert s["paper_all"]["bets"] == 3 and s["paper_all"]["won"] == 2
    assert s["paper_all"]["total_result"] == pytest.approx(won1 + won2 + lost3, abs=1e-6)
    assert s["paper_all"]["average_result"] == pytest.approx((won1 + won2 + lost3) / 3, abs=1e-6)
    assert s["paper_flagged"]["bets"] == 1 and s["paper_flagged"]["average_result"] == pytest.approx(won1, abs=1e-6)
    assert s["enough_games"] is False
    report = format_report(s)
    assert "Fewer than 30 games: too few to conclude anything." in report and "0.1850" in report and "2 after start or unknown" in report


@needs_db
def test_scoring_an_empty_table_says_so_without_failing(fresh_db):
    command.upgrade(alembic_config(), "head")
    s = score_records(fresh_db)
    assert s["used"] == 0 and s["brier_ours"] is None and s["paper_flagged"]["bets"] == 0
    assert "n/a" in format_report(s) and "too few" in format_report(s)


@needs_db
def test_since_limits_the_records(fresh_db):
    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        db.add(scored_record("E1", 0.8, True, 0.6, 0.50, 0.54, "yes"))
        db.commit()
    assert score_records(fresh_db, since=NOW + timedelta(days=1))["records"] == 0
    assert score_records(fresh_db, since=NOW - timedelta(days=1))["records"] == 1


@needs_db
def test_the_score_command_prints_the_report_and_refuses_a_bad_date(fresh_db, monkeypatch, capsys):
    command.upgrade(alembic_config(), "head")
    monkeypatch.setenv("KALSHI_API_BASE", "https://k.test")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    assert cli.main(["score-records"]) == 0
    assert "Records: 0" in capsys.readouterr().out
    assert cli.main(["score-records", "--since", "yesterday"]) == 2
    assert "--since must look like" in capsys.readouterr().err


def test_each_record_has_its_market_kind_and_the_fee_of_its_own_series():
    prediction_ = {**prediction(), "outcomes": [prediction()["outcomes"][0], {**prediction()["outcomes"][1], "kind": "total"}]}
    comparison_ = comparison()
    comparison_["outcomes"][1]["fee"] = {"fee_type": "quadratic", "multiplier": 0.5, "source": "series"}
    a, b = build_records("run1", GAME, prediction_, comparison_, None, NOW)
    assert (a.market_kind, b.market_kind) == ("winner", "total")
    assert (a.fee_type, a.fee_multiplier) == ("quadratic_with_maker_fees", Decimal("0.5")) or a.fee_multiplier == Decimal("1.0")
    assert (b.fee_type, b.fee_multiplier) == ("quadratic", Decimal("0.5"))


@needs_db
def test_scores_are_also_shown_per_kind_of_market(fresh_db):
    command.upgrade(alembic_config(), "head")
    winner = scored_record("E1", 0.8, True, 0.6, 0.50, 0.54, "yes")
    total = scored_record("E2", 0.3, False, 0.5, 0.40, 0.44, "no", no_ask=0.60)
    total.market_kind = "total"
    with DbSession(fresh_db) as db:
        db.add_all([winner, total])
        db.commit()
    s = score_records(fresh_db)
    assert set(s["by_kind"]) == {"winner", "total"}
    assert s["by_kind"]["winner"]["brier_ours"] == pytest.approx(0.04) and s["by_kind"]["total"]["brier_ours"] == pytest.approx(0.09)
    assert s["by_kind"]["total"]["paper_all"]["bets"] == 1 and s["by_kind"]["total"]["same_records"]["n"] == 1
    report = format_report(s)
    assert "  total: 1 outcomes in 1 games, Brier ours 0.0900" in report and "  winner: 1 outcomes" in report


@needs_db
def test_scores_are_also_shown_per_sport_league_and_amount_of_evidence(fresh_db):
    command.upgrade(alembic_config(), "head")
    a = scored_record("KXATPMATCH-X1", 0.8, True, 0.6, 0.50, 0.54, "yes")        # tennis, ATP, 0 claims: Brier 0.04
    b = scored_record("KXATPCHALLENGERMATCH-X2", 0.3, False, 0.5, 0.40, 0.44, "no", no_ask=0.60)  # tennis, Challenger, 3 claims: 0.09
    c = scored_record("KXMLBGAME-X3", 0.6, False, 0.7, 0.50, 0.55, "yes")        # baseball, MLB, 7 claims: 0.36
    d = scored_record("KXNEWGAME-X4", 0.5, True, 0.5, 0.45, 0.50, "yes")         # a series that is not configured: 0.25
    a.supported_claims, b.supported_claims, c.supported_claims, d.supported_claims = 0, 3, 7, 7
    with DbSession(fresh_db) as db:
        db.add_all([a, b, c, d])
        db.commit()
    series = {"KXATPMATCH": ("Tennis", "ATP"), "KXATPCHALLENGERMATCH": ("Tennis", "ATP Challenger"), "KXMLBGAME": ("Baseball", "MLB")}
    s = score_records(fresh_db, series=series, flag_claims=5)
    assert set(s["by_sport"]) == {"Tennis", "Baseball", "unknown"}
    assert s["by_sport"]["Tennis"]["games"] == 2 and s["by_sport"]["Tennis"]["brier_ours"] == pytest.approx((0.04 + 0.09) / 2)
    assert s["by_sport"]["Baseball"]["brier_ours"] == pytest.approx(0.36) and s["by_sport"]["unknown"]["brier_ours"] == pytest.approx(0.25)
    assert set(s["by_league"]) == {"ATP", "ATP Challenger", "MLB", "unknown"}
    assert set(s["by_evidence"]) == {"none", "1 to 4 supported claims", "5 or more supported claims"}
    assert s["by_evidence"]["none"]["brier_ours"] == pytest.approx(0.04) and s["by_evidence"]["5 or more supported claims"]["games"] == 2
    report = format_report(s)
    assert "By sport:" in report and "  Tennis: 2 outcomes in 2 games" in report and "By amount of confirmed evidence:" in report
    assert "too few games: fewer than 5" in report
    without = score_records(fresh_db)  # no series map: the sport and league groups are left out, the rest stays
    assert without["by_sport"] is None and without["by_league"] is None and "By sport:" not in format_report(without)


@needs_db
def test_scores_compare_with_the_bookmakers_where_they_have_a_price(fresh_db):
    command.upgrade(alembic_config(), "head")
    a = scored_record("E1", 0.8, True, 0.6, 0.50, 0.54, "yes")   # ours 0.04, plain AI 0.16, Kalshi 0.52 -> 0.2304
    b = scored_record("E2", 0.3, False, 0.5, 0.40, 0.44, "no", no_ask=0.60)  # ours 0.09, plain AI 0.25, Kalshi 0.42 -> 0.1764
    c = scored_record("E3", 0.6, False, 0.7, 0.50, 0.55, "yes")  # no bookmaker price
    a.book_probability, a.book_pinnacle, a.book_count = Decimal("0.7"), Decimal("0.72"), 40   # 0.09 and 0.0784
    b.book_probability, b.book_count = Decimal("0.2"), 40                                      # 0.04, no Pinnacle
    c.book_note = "no game of the odds feed matched by team names and start time"
    with DbSession(fresh_db) as db:
        db.add_all([a, b, c])
        db.commit()
    bk = score_records(fresh_db)["bookmakers"]
    assert (bk["winner_outcomes"], bk["covered_outcomes"], bk["covered_games"], bk["n"]) == (3, 2, 2, 2)
    assert bk["ours"] == pytest.approx((0.04 + 0.09) / 2) and bk["baseline"] == pytest.approx((0.16 + 0.25) / 2)
    assert bk["market"] == pytest.approx((0.48 ** 2 + 0.42 ** 2) / 2) and bk["book"] == pytest.approx((0.09 + 0.04) / 2)
    assert bk["pinnacle_n"] == 1 and bk["pinnacle"] == pytest.approx(0.0784) and bk["pinnacle_ours"] == pytest.approx(0.04)
    report = format_report(score_records(fresh_db))
    assert "Bookmakers (winner markets only): 2 of 3 scored winner outcomes (2 of 3 games)" in report and "bookmaker consensus 0.0650" in report
    assert "Pinnacle alone, on the 1 that have it: Pinnacle 0.0784 against ours 0.0400" in report


@needs_db
def test_scores_say_so_when_no_outcome_has_a_bookmaker_price(fresh_db):
    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        db.add(scored_record("E1", 0.8, True, 0.6, 0.50, 0.54, "yes"))
        db.commit()
    assert "no scored outcome has a bookmaker price yet" in format_report(score_records(fresh_db))


@needs_db
def test_several_forecasts_of_one_market_score_as_the_latest_before_the_start_and_the_first_is_compared(fresh_db):
    command.upgrade(alembic_config(), "head")
    first = scored_record("E1", 0.20, True, 0.5, 0.50, 0.54, "yes")
    first.created_at = NOW - timedelta(hours=5)
    latest = scored_record("E1", 0.90, True, 0.5, 0.50, 0.54, "yes")
    latest.run_id, latest.created_at = "run-E1-again", NOW - timedelta(hours=1)
    after_start = scored_record("E1", 0.99, True, 0.5, 0.50, 0.54, "yes", before=False)  # made after the start: never used
    after_start.run_id, after_start.created_at = "run-E1-late", NOW
    other = scored_record("E2", 0.30, False, 0.5, 0.40, 0.44, "no", no_ask=0.60)  # forecast once
    with DbSession(fresh_db) as db:
        db.add_all([first, latest, after_start, other])
        db.commit()
    s = score_records(fresh_db)
    assert s["used"] == 2 and s["games"] == 2  # one per market
    assert s["brier_ours"] == pytest.approx(((0.9 - 1) ** 2 + 0.3 ** 2) / 2)  # the latest of E1 (0.90), not 0.20 or 0.99
    assert s["updated"]["markets"] == 1 and s["updated"]["brier_first"] == pytest.approx(0.64) and s["updated"]["brier_latest"] == pytest.approx(0.01)
    assert "1 markets were forecast more than once: Brier of the first forecast 0.6400, of the latest 0.0100" in format_report(s)
