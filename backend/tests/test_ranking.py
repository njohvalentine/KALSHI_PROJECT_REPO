"""The ranked list of outcomes (FEAT-20261022-0955): the side, the gap, the two orders, the filters, the confidence rule and its reasons, the risks, the endpoint, the label check. No model call."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy.orm import Session as DbSession

from app.config import load_settings
from app.models import OutcomeRecord, Run
from app.opportunities import collect
from app.ranking import arrange, build_ranking, confidence, confidence_vs_accuracy
from tests.conftest import alembic_config, needs_db
from tests.test_opportunities import BASE, GOOD, GOOD_BASELINE, NOW, FakeKalshi, add_run, event, kalshi_for_good, market, outcome, prediction

SETTINGS = load_settings(BASE)
TIERS = {"official": 6, "news": 2, "other": 1}


@pytest.mark.parametrize("kw,level,why", [
    (dict(stale=False, supported=11, spread=0.03, tiers=TIERS), "high", "11 supported facts"),
    (dict(stale=False, supported=11, spread=0.03, tiers=None), "medium", "source kinds are not known"),  # an older run has no tier counts: never "high"
    (dict(stale=False, supported=11, spread=0.03, tiers={"official": 1, "news": 1, "other": 9}), "medium", "from official or news sources"),
    (dict(stale=False, supported=7, spread=0.03, tiers=TIERS), "medium", "7 supported facts"),
    (dict(stale=False, supported=11, spread=0.07, tiers=TIERS), "medium", "7 points"),
    (dict(stale=True, supported=11, spread=0.03, tiers=TIERS), "low", "older than"),
    (dict(stale=False, supported=3, spread=0.03, tiers=TIERS), "low", "only 3 supported facts"),
    (dict(stale=False, supported=0, spread=0.03, tiers=None), "low", "no supported facts"),
    (dict(stale=False, supported=11, spread=0.12, tiers=TIERS), "low", "12 points"),
])
def test_the_confidence_rule_and_its_reasons(kw, level, why):
    got = confidence(settings=SETTINGS, **kw)
    assert got["level"] == level and any(why in r for r in got["reasons"]), got


def rows_for(engine, kalshi, **env):
    settings = load_settings(BASE | env)
    return asyncio.run(build_ranking(engine, kalshi, settings, {}, now=NOW))


def migrated(fresh_db):
    command.upgrade(alembic_config(), "head")
    return fresh_db


@needs_db
def test_one_row_per_market_on_its_more_probable_side_with_that_sides_price_and_gap(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    result = rows_for(engine, kalshi_for_good())
    by = {r["market_ticker"]: r for r in result["rows"]}
    assert set(by) == {"KX-1-H", "KX-1-A", "KXTTOTAL-1-1"} and result["games_considered"] == 1
    home, away, over = by["KX-1-H"], by["KX-1-A"], by["KXTTOTAL-1-1"]
    assert (home["side"], home["our_probability"], home["price"]) == ("yes", 0.55, 0.42)
    assert (away["side"], away["our_probability"], away["price"]) == ("no", 0.55, 0.43)  # 45 percent for the team, so the likelier bet is "no" at 1 minus the bid
    assert (over["side"], over["our_probability"], over["price"]) == ("yes", 0.7, 0.52)
    assert home["range"] == {"low": 0.5, "high": 0.6} and away["range"] == {"low": 0.5, "high": 0.6}  # the mirrored range for the "no" side
    assert home["market"] == "Home wins" and home["title"] == "Home vs Away" and home["run_id"] == "run-KX-1"


@needs_db
def test_the_gap_is_the_comparisons_edge_for_the_same_side(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    kalshi = kalshi_for_good()
    comparison = {c["market_ticker"]: c for c in asyncio.run(collect(engine, kalshi, SETTINGS, {}, NOW))[0][1]["outcomes"]}
    by = {r["market_ticker"]: r for r in rows_for(engine, kalshi_for_good())["rows"]}
    for ticker, row in by.items():
        assert row["gap"] == pytest.approx(comparison[ticker][row["side"]]["net_edge"], abs=1e-6)  # the same arithmetic as the run's comparison


@needs_db
def test_the_two_orders_and_the_filters(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
    rows = rows_for(engine, kalshi_for_good())["rows"]
    by_probability = arrange(rows, sort="probability", hide_at=1.0, sport=None, kind=None)
    assert [r["market_ticker"] for r in by_probability][0] == "KXTTOTAL-1-1" and [r["our_probability"] for r in by_probability] == sorted((r["our_probability"] for r in rows), reverse=True)
    by_gap = arrange(rows, sort="gap", hide_at=1.0, sport=None, kind=None)
    assert [r["gap"] for r in by_gap] == sorted((r["gap"] for r in rows), reverse=True)
    assert [r["market_ticker"] for r in arrange(rows, "probability", 0.5, None, None)] == ["KX-1-H", "KX-1-A"]  # priced at 50 cents or more is hidden (the total at 52)
    assert [r["market_ticker"] for r in arrange(rows, "probability", 1.0, None, "total")] == ["KXTTOTAL-1-1"]
    assert arrange(rows, "probability", 1.0, "Tennis", None) == [] and len(arrange(rows, "probability", 1.0, None, None)) == 3
    assert len(arrange(rows, "probability", 1.0, None, None, limit=2)) == 2


@needs_db
def test_a_game_that_has_started_is_left_out(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE, start_in_hours=-1)
    assert rows_for(engine, kalshi_for_good())["rows"] == []


@needs_db
def test_a_stale_forecast_is_low_confidence_with_a_risk_and_never_flagged(fresh_db):
    engine = migrated(fresh_db)
    add_run(engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE, finished_hours_ago=30)
    rows = rows_for(engine, kalshi_for_good())["rows"]
    assert rows and all(r["confidence"]["level"] == "low" and r["flagged"] is False and any("hours old" in x for x in r["risks"]) for r in rows)


@needs_db
def test_risks_name_a_big_disagreement_with_the_price_and_no_price(fresh_db):
    engine = migrated(fresh_db)
    big = prediction(outcome("KX-1-H", "Home wins", 0.75, 0.70, 0.80), outcome("KX-1-A", "Away wins", 0.25, 0.20, 0.30))
    add_run(engine, "KX-1", "Home vs Away", big, baseline={"KX-1-H": 0.5, "KX-1-A": 0.5})
    kalshi = FakeKalshi({"KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.50", "0.52"))})  # no market for the away team
    by = {r["market_ticker"]: r for r in rows_for(engine, kalshi)["rows"]}
    assert any("15 points" in x for x in by["KX-1-H"]["risks"])  # 75 against 52: a model error is more likely than an opportunity
    assert by["KX-1-A"]["price"] is None and by["KX-1-A"]["gap"] is None and any("no Kalshi price" in x for x in by["KX-1-A"]["risks"])


@needs_db
def test_the_endpoint_needs_login_arranges_the_rows_caches_and_carries_the_accuracy(make_client):
    from tests.conftest import EMAIL, PASSWORD

    client = make_client()
    client.__enter__()
    try:
        assert client.get("/api/ranking").status_code == 401
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers={"X-Requested-With": "t"})
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
        kalshi = kalshi_for_good()
        client.app.state.kalshi = kalshi
        data = client.get("/api/ranking").json()
        calls = len(kalshi.calls)
        assert [r["market_ticker"] for r in data["rows"]][0] == "KXTTOTAL-1-1" and data["total_rows"] == 3 and data["games_considered"] == 1
        assert data["sports"] == [] and data["kinds"] == ["total", "winner"] and set(data["accuracy"]) == {"games", "ours", "kalshi"}
        by_gap = client.get("/api/ranking?sort=gap").json()["rows"]
        assert [r["gap"] for r in by_gap] == sorted((r["gap"] for r in by_gap), reverse=True) and len(kalshi.calls) == calls  # another order is served from the cache
        assert len(client.get("/api/ranking?limit=1").json()["rows"]) == 1 and len(client.get("/api/ranking?hide_at=0.5").json()["rows"]) == 2
        assert client.get("/api/ranking?sort=nonsense").status_code == 422 and client.get("/api/ranking?hide_at=0").status_code == 422
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_the_label_check_reports_the_brier_score_of_our_probability_inside_each_label(fresh_db):
    engine = migrated(fresh_db)

    def rec(i, spread, claims, p, yes, mid):
        lo, hi = p - spread / 2, p + spread / 2
        return OutcomeRecord(run_id=f"r{i}", event_ticker=f"K{i}", market_ticker=f"K{i}-T", outcome="o", game_start=NOW, created_at=NOW, before_start=True, probability=p, prob_min=lo, prob_max=hi,
                             forecasters_valid=3, evidence="supported", supported_claims=claims, resolved_yes=yes, yes_bid=mid - 0.01, yes_ask=mid + 0.01, market_kind="winner")
    with DbSession(engine) as db:
        for i in range(4):
            db.add(Run(id=f"r{i}", event_ticker=f"K{i}", event_title="t", status="done", created_at=NOW))
        db.flush()
        db.add_all([rec(0, 0.03, 12, 0.9, True, 0.8), rec(1, 0.03, 12, 0.9, False, 0.8), rec(2, 0.15, 12, 0.5, True, 0.5), rec(3, 0.03, 2, 0.5, False, 0.5)])
        db.commit()
    out = confidence_vs_accuracy(engine, SETTINGS)
    assert out["medium_or_high"]["n"] == 2 and out["low"]["n"] == 2  # tiers are unknown in records, so nothing is "high": the strongest label here is "medium"
    assert out["medium_or_high"]["ours"] == pytest.approx(((0.9 - 1) ** 2 + (0.9 - 0) ** 2) / 2) and out["medium_or_high"]["kalshi"] == pytest.approx(((0.8 - 1) ** 2 + (0.8 - 0) ** 2) / 2)
