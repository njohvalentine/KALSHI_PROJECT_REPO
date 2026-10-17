"""NO BET, or worth a look: one rule for the Opportunities page, the run page and the alerts."""

import re

import pytest

from app import verdict as v
from app.config import load_settings
from app.monitor import alert_text
from app.verdict import track_kind, verdict
from tests.conftest import needs_db
from tests.fakes import FakeModel
from tests.test_dashboard import many_games
from tests.test_runs import signed_in, start, wait_done

ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}


def no_bare_bet(text):
    return not re.search(r"(?<!NO )\bBET\b", text)


def test_nothing_flagged_is_no_bet_with_the_reason():
    assert verdict(0, False, False, True, "ahead")["kind"] == "no_bet"
    assert "no market passed all the tests" in verdict(0, False, False, True, "ahead")["text"]


def test_an_old_forecast_or_no_price_is_no_bet_even_if_something_was_flagged():
    old = verdict(2, True, False, True, "ahead", age_hours=20)
    assert old["kind"] == "no_bet" and "20 hours old" in old["text"] and "Research the game again" in old["text"]
    assert verdict(2, False, True, True, "ahead")["kind"] == "no_bet"


def test_a_flag_carries_the_caution_until_the_track_record_and_the_sport_are_proven():
    a = verdict(1, False, False, True, "no_edge")
    assert a["kind"] == "look_caution" and a["label"] == "Worth a look" and a["text"].startswith("Worth a look. NO BET is the default")
    assert "have not beaten the Kalshi price" in a["caution"]
    assert "too few games have finished" in verdict(1, False, False, True, "too_few")["caution"]
    b = verdict(1, False, False, False, "ahead")
    assert b["kind"] == "look_caution" and "no scored results yet: the flag has not been tested here" in b["caution"]
    both = verdict(1, False, False, False, "no_edge")["caution"]
    assert "Kalshi price" in both and "has not been tested here" in both


def test_only_a_flag_in_a_measured_sport_with_a_proven_track_record_is_plain_worth_a_look():
    a = verdict(3, False, False, True, "ahead")
    assert a["kind"] == "look" and a["caution"] is None and "not a recommendation" in a["text"]


@pytest.mark.parametrize("args", [(0, False, False, True, "ahead"), (2, True, False, True, "ahead", 20.0), (1, False, False, True, "no_edge"),
                                  (1, False, False, False, "too_few"), (3, False, False, True, "ahead"), (1, False, True, None, "ahead")])
def test_the_word_bet_never_appears_without_no_in_front_of_it(args):
    r = verdict(*args)
    assert no_bare_bet(r["text"]) and no_bare_bet(r["label"]) and no_bare_bet(r["caution"] or "")


def test_the_alerts_carry_the_caution_and_the_no_longer_flagged_alert_says_no_bet():
    game = {"title": "A vs B", "finished_at": __import__("datetime").datetime(2026, 10, 13, tzinfo=__import__("datetime").UTC)}
    now = game["finished_at"]
    best = {"best": {"market": "A wins", "side": "yes", "price": 0.4, "gap": 0.1, "count": 1}}
    row = {"supported_claims": 7, "verdict": verdict(1, False, False, True, "no_edge")}
    assert "NO BET is the default" in alert_text("run_flagged", game, row, now, best)
    assert "NO BET is the default" in alert_text("start_soon", game, row, now, {})
    assert alert_text("no_longer_flagged", game, row, now, {}).count("NO BET.") == 1
    proven = {"supported_claims": 7, "verdict": verdict(1, False, False, True, "ahead")}
    assert "NO BET" not in alert_text("run_flagged", game, proven, now, best)


@needs_db
def test_the_track_kind_follows_the_scores_and_is_cached_for_a_minute(make_client, monkeypatch):
    make_client()  # a migrated empty database
    engine = make_client.engine
    settings = load_settings(ENV)
    v._track_cache.clear()
    assert track_kind(engine, settings) == "too_few"
    many_games(engine, 31)  # more than the 30 games a verdict needs: the numbers decide
    assert track_kind(engine, settings) == "too_few"  # still the cached answer
    clock = {"t": 1000.0}
    monkeypatch.setattr(v.time, "monotonic", lambda: clock["t"])
    v._track_cache.clear()
    first = track_kind(engine, settings)
    assert first in ("ahead", "no_edge")  # 31 games: no longer "too few"
    clock["t"] += 30
    assert track_kind(engine, settings) == first
    clock["t"] += 31
    assert track_kind(engine, settings) == first  # recomputed after a minute, same data, same answer


@needs_db
def test_a_run_detail_carries_the_verdict_only_when_the_run_is_done(make_client):
    client = signed_in(make_client, FakeModel(delay=0.3))
    try:
        started = start(client).json()["id"]
        assert client.get(f"/api/runs/{started}").json()["verdict"] is None  # still running
        done = wait_done(client, started)
        assert done["status"] == "done"
        answer = client.get(f"/api/runs/{started}").json()["verdict"]
        assert answer["kind"] == "no_bet" and "no forecast" in answer["text"]  # the fake model has no forecaster behind it
    finally:
        client.__exit__(None, None, None)
