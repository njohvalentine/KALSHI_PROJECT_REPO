"""The Opportunities page: ranking from stored forecasts and live prices. No model is called in any of these tests."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy.orm import Session as DbSession

from app.config import load_settings
from app.kalshi import KalshiError
from app.models import OutcomeRecord, Run
from app.opportunities import build_opportunities
from tests.conftest import EMAIL, PASSWORD, alembic_config, needs_db

pytestmark = needs_db
H = {"X-Requested-With": "t"}
NOW = datetime.now(UTC)
BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}


def market(ticker, bid, ask, size="200", bid_size="150"):
    return {"ticker": ticker, "yes_bid_dollars": bid, "yes_ask_dollars": ask, "yes_ask_size_fp": size, "yes_bid_size_fp": bid_size}


class FakeKalshi:
    def __init__(self, events, broken=()):
        self.events, self.broken, self.calls = events, set(broken), []

    def get_event(self, ticker):
        self.calls.append(ticker)
        if ticker in self.broken:
            raise KalshiError("down")
        return self.events[ticker]

    def close(self):
        pass

    def get_series(self, ticker):
        self.calls.append(("series", ticker))
        return {"series": {"fee_type": "quadratic", "fee_multiplier": 1}}


def event(ticker, series, *markets):
    return {"event": {"event_ticker": ticker, "series_ticker": series}, "markets": list(markets)}


def outcome(ticker, label, p, lo, hi, kind="winner"):
    return {"market_ticker": ticker, "kind": kind, "outcome": label, "probability": p, "min": lo, "max": hi, "spread": round(hi - lo, 4), "median_raw": p, "forecasts": []}


def prediction(*outcomes, claims=7, evidence="supported"):
    return {"outcomes": list(outcomes), "evidence": evidence, "supported_claims": claims, "forecasters_valid": 3, "dropped": [], "markets_not_offered": [], "adjustments": []}


def add_run(engine, ticker, title, pred, finished_hours_ago=1, start_in_hours=5, status="done", baseline=None, run_id=None):
    run_id = run_id or f"run-{ticker}"
    finished = NOW - timedelta(hours=finished_hours_ago)
    with DbSession(engine) as db:
        db.add(Run(id=run_id, event_ticker=ticker, event_title=title, status=status, prediction=pred, finished_at=finished, created_at=finished))
        for o in (pred or {}).get("outcomes", []):
            db.add(OutcomeRecord(
                run_id=run_id, event_ticker=ticker, market_ticker=o["market_ticker"], outcome=o["outcome"], game_start=NOW + timedelta(hours=start_in_hours),
                created_at=finished, before_start=True, probability=o["probability"], prob_min=o["min"], prob_max=o["max"], forecasters_valid=3,
                evidence="supported", supported_claims=7, baseline_probability=(baseline or {}).get(o["market_ticker"]),
            ))
        db.commit()


GOOD = prediction(outcome("KX-1-H", "Home wins", 0.55, 0.50, 0.60), outcome("KX-1-A", "Away wins", 0.45, 0.40, 0.50),
                  outcome("KXTTOTAL-1-1", "Over 1.5 goals scored", 0.70, 0.65, 0.75, kind="total"))
GOOD_BASELINE = {"KX-1-H": 0.45, "KX-1-A": 0.55, "KXTTOTAL-1-1": 0.60}


def kalshi_for_good():
    return FakeKalshi({
        "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.40", "0.42"), market("KX-1-A", "0.57", "0.59")),
        "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
    })


def run(engine, kalshi, show_all=False, **env):
    return asyncio.run(build_opportunities(engine, kalshi, load_settings(BASE | env), {}, show_all, now=NOW))


def migrated(fresh_db):
    command.upgrade(alembic_config(), "head")
    return fresh_db


def test_one_row_per_game_with_the_best_flagged_market_the_live_gap_and_the_mirror_counted_once(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    result = run(engine, kalshi_for_good())
    assert result["games_considered"] == 1 and result["flagged_games"] == 1 and len(result["opportunities"]) == 1
    row = result["opportunities"][0]
    assert row["flagged"] and row["title"] == "Home vs Away" and row["supported_claims"] == 7 and row["stale"] is False
    # "yes" on Home at 0.42 and "no" on Away at 0.43 are almost the same bet; the total is over the plausibility limit (0.163 > 0.15)
    assert row["flagged_markets"] == 1
    best = row["best"]
    assert best["market_ticker"] in ("KX-1-H", "KX-1-A") and best["gap"] > 0.05
    assert best["market_ticker"] == "KX-1-H" and best["side"] == "yes" and best["price"] == 0.42 and best["our_probability"] == 0.55 and best["spread"] == 0.1


def test_the_gap_is_recomputed_with_todays_prices(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    before = run(engine, kalshi_for_good())["opportunities"][0]
    assert before["best"]["market_ticker"] == "KX-1-H" and before["best"]["price"] == 0.42
    moved = FakeKalshi({
        "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.50", "0.52"), market("KX-1-A", "0.47", "0.49")),
        "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
    })
    result = run(engine, moved, show_all=True)  # the price moved toward our view: the gap shrank below the minimum, so the game is not flagged
    row = result["opportunities"][0]
    assert row["flagged"] is False and row["flagged_markets"] == 0
    assert row["best"]["market_ticker"] == "KXTTOTAL-1-1" and any("model error" in r for r in row["best"]["reasons"])  # the largest gap left is over the limit


def test_started_games_games_without_a_forecast_and_failed_runs_are_left_out(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Good", GOOD, baseline=GOOD_BASELINE)
    add_run(engine, "KX-2", "Started", GOOD, start_in_hours=-1, baseline=GOOD_BASELINE)
    add_run(engine, "KX-4", "No forecast", {"unavailable": "Only 1 valid forecast(s)"})
    add_run(engine, "KX-5", "Failed", None, status="failed")
    result = run(engine, kalshi_for_good(), show_all=True)
    assert [r["title"] for r in result["opportunities"]] == ["Good"] and result["games_considered"] == 1


def test_the_latest_run_of_a_game_is_the_one_used(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, finished_hours_ago=5, baseline=GOOD_BASELINE, run_id="old")
    newer = prediction(outcome("KX-1-H", "Home wins", 0.60, 0.58, 0.62), outcome("KX-1-A", "Away wins", 0.40, 0.38, 0.42))
    add_run(engine, "KX-1", "Home vs Away", newer, finished_hours_ago=1, baseline={"KX-1-H": 0.50, "KX-1-A": 0.50}, run_id="new")
    row = run(engine, kalshi_for_good(), show_all=True)["opportunities"][0]
    assert row["run_id"] == "new"


def test_an_old_forecast_is_shown_greyed_and_never_flagged(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, finished_hours_ago=20, baseline=GOOD_BASELINE)
    assert run(engine, kalshi_for_good())["opportunities"] == []  # not flagged, so not in the default list
    row = run(engine, kalshi_for_good(), show_all=True)["opportunities"][0]
    assert row["stale"] is True and row["flagged"] is False and row["age_hours"] == 20.0 and "20 hours old" in row["risks"][0]
    assert run(engine, kalshi_for_good(), show_all=False, OPPORTUNITY_MAX_AGE_HOURS="48")["flagged_games"] == 1  # the age limit is a setting


def test_a_game_whose_prices_cannot_be_read_is_listed_and_never_flagged(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    row = run(engine, FakeKalshi({}, broken=["KX-1"]), show_all=True)["opportunities"][0]
    assert row["flagged"] is False and row["best"] is None and "Kalshi prices could not be read" in row["unavailable"]


def test_ranking_puts_flagged_games_first_by_gap_and_the_empty_state_explains_itself(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Flagged", GOOD, baseline=GOOD_BASELINE)
    flat = prediction(outcome("KX-7-H", "Home wins", 0.44, 0.43, 0.45), outcome("KX-7-A", "Away wins", 0.56, 0.55, 0.57))
    add_run(engine, "KX-7", "Not flagged", flat, finished_hours_ago=2, baseline={"KX-7-H": 0.44, "KX-7-A": 0.56})
    kalshi = kalshi_for_good()
    kalshi.events["KX-7"] = event("KX-7", "KXTGAME", market("KX-7-H", "0.43", "0.45"), market("KX-7-A", "0.54", "0.56"))
    result = run(engine, kalshi, show_all=True)
    assert [r["title"] for r in result["opportunities"]] == ["Flagged", "Not flagged"] and result["flagged_games"] == 1
    only_flat = run(engine, kalshi, show_all=False, MIN_RESEARCH_SHIFT="0.9")  # nothing can be flagged now
    assert only_flat["opportunities"] == [] and only_flat["flagged_games"] == 0
    assert only_flat["top_reasons"] and all("games" in r and "reason" in r for r in only_flat["top_reasons"])
    assert any("did not move the forecast" in r["reason"] for r in only_flat["top_reasons"])


def test_the_fee_of_a_series_is_read_once_for_many_games(fresh_db):
    engine = migrated(fresh_db)
    for i in (1, 3):
        pred = prediction(outcome(f"KX-{i}-H", "Home wins", 0.55, 0.50, 0.60), outcome(f"KX-{i}-A", "Away wins", 0.45, 0.40, 0.50))
        add_run(engine, f"KX-{i}", f"Game {i}", pred, baseline={f"KX-{i}-H": 0.45, f"KX-{i}-A": 0.55})
    kalshi = FakeKalshi({f"KX-{i}": event(f"KX-{i}", "KXTGAME", market(f"KX-{i}-H", "0.40", "0.42"), market(f"KX-{i}-A", "0.57", "0.59")) for i in (1, 3)})
    cache = {}
    asyncio.run(build_opportunities(engine, kalshi, load_settings(BASE | {"SPORTS_FETCH_CONCURRENCY": "1"}), cache, True, now=NOW))  # one at a time, so the second game finds the fee cached
    assert kalshi.calls.count(("series", "KXTGAME")) == 1 and "KXTGAME" in cache


def test_the_endpoint_needs_login_calls_no_model_and_caches_for_a_minute(make_client):
    client = make_client()
    client.__enter__()
    try:
        assert client.get("/api/opportunities").status_code == 401
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
        kalshi = kalshi_for_good()
        client.app.state.kalshi = kalshi
        first = client.get("/api/opportunities").json()
        calls = len(kalshi.calls)
        second = client.get("/api/opportunities").json()
        assert first == second and len(kalshi.calls) == calls  # cached
        assert first["flagged_games"] == 1 and first["opportunities"][0]["title"] == "Home vs Away"
        assert client.app.state.judge is None and client.app.state.forecaster is None  # nothing that could call a model is even configured here
        shown_all = client.get("/api/opportunities?all=true").json()
        assert shown_all["games_considered"] == 1
    finally:
        client.__exit__(None, None, None)
