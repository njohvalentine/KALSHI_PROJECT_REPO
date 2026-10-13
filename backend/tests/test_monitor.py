"""The watcher: alerts and automatic research, with fakes only (no model, no network, no chat channel)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Alert, Run
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.test_opportunities import GOOD, GOOD_BASELINE, FakeKalshi, add_run, event, kalshi_for_good, market, outcome, prediction

pytestmark = needs_db
H = {"X-Requested-With": "t"}
NOW = datetime.now(UTC)


def flagged_prediction():
    """GOOD with the comparison the run itself stored: Home flagged at forecast time."""
    p = {**GOOD}
    p["comparison"] = {"outcomes": [
        {"market_ticker": "KX-1-H", "meaningful": True, "net_edge": 0.113, "side": "yes", "yes_ask": 0.42, "no_ask": 0.60, "reasons": []},
        {"market_ticker": "KX-1-A", "meaningful": True, "net_edge": 0.103, "side": "no", "yes_ask": 0.59, "no_ask": 0.43, "reasons": []},
        {"market_ticker": "KXTTOTAL-1-1", "meaningful": False, "net_edge": 0.163, "side": "yes", "yes_ask": 0.52, "no_ask": 0.50, "reasons": ["gap above 0.15"]},
    ]}
    return p


def add_records_with_prices(engine, run_id="run-KX-1", mids=None):
    """add_run writes records without market prices; add the prices the forecast saw (Home 0.40 to 0.42, Away 0.57 to 0.59)."""
    with DbSession(engine) as db:
        for ticker, bid, ask in (("KX-1-H", "0.40", "0.42"), ("KX-1-A", "0.57", "0.59"), ("KXTTOTAL-1-1", "0.50", "0.52")):
            db.execute(text("UPDATE outcome_records SET yes_bid=:b, yes_ask=:a WHERE run_id=:r AND market_ticker=:t"), {"b": bid, "a": ask, "r": run_id, "t": ticker})
        db.commit()


@pytest.fixture
def app_client(make_client):
    def build(**env):
        client = make_client(**env)
        client.__enter__()
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        client.app.state.kalshi = kalshi_for_good()
        return client
    return build


def alerts(engine):
    with DbSession(engine) as db:
        return db.query(Alert).order_by(Alert.id).all()


def cycle(client, now=None):
    asyncio.run(client.app.state.monitor.cycle(now or NOW))


def test_a_finished_run_with_markets_worth_a_look_makes_one_alert_that_is_not_repeated(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        cycle(client)
        cycle(client)  # a second cycle, as ten minutes later: nothing new
        rows = alerts(make_client.engine)
        assert [a.kind for a in rows] == ["run_flagged"] and rows[0].status == "recorded" and rows[0].run_id == "run-KX-1"
        text_ = rows[0].text
        assert "Worth a look: Home vs Away" in text_ and "Buy “yes” on Home wins at 42¢" in text_ and "+11¢" in text_
        assert "7 supported claims" in text_ and "1 h ago" in text_ and "not a recommendation" in text_
    finally:
        client.__exit__(None, None, None)


def test_a_large_market_move_asks_to_research_again_and_does_not_call_it_an_opportunity(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.28", "0.30"), market("KX-1-A", "0.69", "0.71")),  # Home fell 12 cents
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        cycle(client)
        moved = [a for a in alerts(make_client.engine) if a.kind == "market_moved"]
        assert len(moved) == 1 and "moved 12¢ on" in moved[0].text and ("Home wins" in moved[0].text or "Away wins" in moved[0].text)  # both sides moved
        assert "may know something we do not" in moved[0].text
        assert "researching again" in moved[0].text and "opportunity" not in moved[0].text.lower()
    finally:
        client.__exit__(None, None, None)


def test_a_small_move_makes_no_alert(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.43", "0.45"), market("KX-1-A", "0.54", "0.56")),  # 3 cents
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        cycle(client)
        assert [a for a in alerts(make_client.engine) if a.kind == "market_moved"] == []
    finally:
        client.__exit__(None, None, None)


def test_markets_that_were_flagged_and_no_longer_are_reported_once(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        cycle(client)  # worth a look at the prices of the forecast: the user is told
        assert [a.kind for a in alerts(make_client.engine)] == ["run_flagged"]
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.50", "0.52"), market("KX-1-A", "0.47", "0.49")),  # the gap closed
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        cycle(client)
        cycle(client)
        kinds = [a.kind for a in alerts(make_client.engine)]
        assert kinds.count("no_longer_flagged") == 1
    finally:
        client.__exit__(None, None, None)


def test_nothing_is_said_about_a_game_that_was_never_reported_as_worth_a_look(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE)  # stored as flagged under older rules
        add_records_with_prices(make_client.engine)
        client.app.state.kalshi = FakeKalshi({
            "KX-1": event("KX-1", "KXTGAME", market("KX-1-H", "0.50", "0.52"), market("KX-1-A", "0.47", "0.49")),
            "KXTTOTAL-1": event("KXTTOTAL-1", "KXTTOTAL", market("KXTTOTAL-1-1", "0.50", "0.52")),
        })
        cycle(client)
        assert [a.kind for a in alerts(make_client.engine) if a.kind in ("run_flagged", "no_longer_flagged")] == []  # not flagged now, and we never said it was
    finally:
        client.__exit__(None, None, None)


def test_a_game_worth_a_look_that_starts_soon_gets_a_reminder(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, baseline=GOOD_BASELINE, start_in_hours=0.5)
        add_records_with_prices(make_client.engine)
        cycle(client)
        soon = [a for a in alerts(make_client.engine) if a.kind == "start_soon"]
        assert len(soon) == 1 and "Starting soon: Home vs Away" in soon[0].text and "lineups may have changed" in soon[0].text
    finally:
        client.__exit__(None, None, None)


def test_old_forecasts_and_started_games_make_no_alerts(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Old", flagged_prediction(), finished_hours_ago=30, baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        add_run(make_client.engine, "KX-2", "Started", flagged_prediction(), start_in_hours=-1, baseline=GOOD_BASELINE)
        cycle(client)
        assert alerts(make_client.engine) == []
    finally:
        client.__exit__(None, None, None)


def test_the_hourly_limit_and_the_cooldown_hold_alerts_back_and_say_so(app_client, make_client):
    client = app_client(ALERT_MAX_PER_HOUR="1")
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE, start_in_hours=0.5)
        add_records_with_prices(make_client.engine)
        cycle(client)  # run_flagged and start_soon are both due: the first is recorded, the second held back by the hourly limit
        rows = alerts(make_client.engine)
        assert [(a.kind, a.status) for a in rows] == [("run_flagged", "recorded"), ("start_soon", "held_back")]
        assert rows[1].detail == "hourly limit of 1 alerts reached"
        cycle(client)  # held-back alerts are not retried and not repeated
        assert len(alerts(make_client.engine)) == 2
    finally:
        client.__exit__(None, None, None)
    client = app_client(ALERT_COOLDOWN_MINUTES="60")
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE, run_id="newer", finished_hours_ago=0.2)
        cycle(client)
        held = [a for a in alerts(make_client.engine) if a.run_id == "newer"]
        assert held and held[0].status == "held_back" and held[0].detail.startswith("cooldown")
    finally:
        client.__exit__(None, None, None)


def test_a_chat_channel_that_fails_is_recorded_by_error_kind_only(app_client, make_client, caplog):
    client = app_client()
    try:
        async def broken(message):
            raise ConnectionError("https://api.telegram.org/bot123:SECRET-TOKEN/sendMessage refused")
        client.app.state.notifier = broken
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        with caplog.at_level(logging.WARNING):
            cycle(client)
        row = alerts(make_client.engine)[0]
        assert row.status == "failed" and row.detail == "ConnectionError" and "SECRET-TOKEN" not in caplog.text and "SECRET-TOKEN" not in str(row.text)
        sent = []
        async def working(message):
            sent.append(message)
        client.app.state.notifier = working
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE, run_id="second", finished_hours_ago=0.1)
        cycle(client, NOW + timedelta(hours=3))
        assert sent and any(a.status == "sent" for a in alerts(make_client.engine))
    finally:
        client.__exit__(None, None, None)


def test_the_alerts_endpoint_shows_the_history_and_the_state_of_the_watcher(app_client, make_client):
    client = app_client()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", flagged_prediction(), baseline=GOOD_BASELINE)
        add_records_with_prices(make_client.engine)
        before = client.get("/api/alerts").json()
        assert before["alerts"] == [] and before["monitor"]["enabled"] is False and before["monitor"]["channel"] == "app only"
        cycle(client)
        after = client.get("/api/alerts").json()
        assert after["alerts"][0]["kind"] == "run_flagged" and after["monitor"]["last_cycle_at"] and after["monitor"]["last_error"] is None
        assert after["monitor"]["auto_research_cap"] == 0
    finally:
        client.__exit__(None, None, None)


def test_a_failing_cycle_is_survived_and_shown(app_client, make_client, monkeypatch):
    client = app_client()
    try:
        import app.monitor as monitor_module

        async def boom(*a, **k):
            raise RuntimeError("secret detail")
        monkeypatch.setattr(monitor_module, "collect", boom)
        cycle(client)
        state = client.get("/api/alerts").json()["monitor"]
        assert state["last_error"] == "RuntimeError" and "secret detail" not in str(state)
    finally:
        client.__exit__(None, None, None)


def test_the_alerts_endpoint_needs_login(make_client):
    client = make_client()
    with client:
        assert client.get("/api/alerts").status_code == 401


# ---- automatic research -------------------------------------------------------------------------------------

class FakeGames:
    def __init__(self, games):
        self.games = games

    def query(self, sport=None, q=None, limit=200, include_started=False):
        return {"games": self.games}


def game(ticker, hours_ahead, volume="100"):
    return {"event_ticker": ticker, "starts_at": (NOW + timedelta(hours=hours_ahead)).isoformat(), "outcomes": [{"volume": volume}]}


class StartRecorder:
    def __init__(self, fail=None):
        self.started, self.fail = [], fail

    async def __call__(self, app, ticker, user_id, trigger="manual"):
        from app.runs import RunStartError
        if self.fail:
            raise RunStartError(*self.fail)
        self.started.append((ticker, user_id, trigger))
        with DbSession(app.state.engine) as db:
            db.add(Run(id=f"auto-{ticker}", event_ticker=ticker, event_title=ticker, status="queued", trigger=trigger))
            db.commit()
        return {"id": f"auto-{ticker}", "status": "queued"}


def auto_client(app_client, monkeypatch, games, **env):
    import app.monitor as monitor_module

    client = app_client(**env)
    client.app.state.games = FakeGames(games)
    client.app.state.research_graph = object()  # research is "configured" for the purposes of this rule
    recorder = StartRecorder()
    monkeypatch.setattr(monitor_module, "start_game_run", recorder)
    return client, recorder


def test_automatic_research_is_off_by_default(app_client, monkeypatch):
    client, recorder = auto_client(app_client, monkeypatch, [game("KX-A", 2)])
    try:
        cycle(client)
        assert recorder.started == []
    finally:
        client.__exit__(None, None, None)


def test_automatic_research_takes_the_soonest_games_in_the_window_up_to_the_daily_cap(app_client, make_client, monkeypatch):
    games = [game("KX-LATE", 20), game("KX-SOON", 2), game("KX-FAR", 40), game("KX-MID", 6), game("KX-NOSTART", 0)]
    games[-1]["starts_at"] = None
    client, recorder = auto_client(app_client, monkeypatch, games, AUTO_RESEARCH_MAX_PER_DAY="2", MAX_CONCURRENT_RUNS="5")
    try:
        cycle(client)
        assert recorder.started == [("KX-SOON", None, "auto"), ("KX-MID", None, "auto")]  # soonest first, 2 of the cap, the 40 h game is outside 24 h
        cycle(client)  # the cap of two a day is used up (counted from the runs table)
        assert len(recorder.started) == 2
        assert client.get("/api/alerts").json()["monitor"]["auto_research_started_today"] == 2
    finally:
        client.__exit__(None, None, None)


def test_a_game_researched_recently_is_not_researched_again_and_ties_go_to_the_busier_market(app_client, make_client, monkeypatch):
    client, recorder = auto_client(app_client, monkeypatch, [game("KX-A", 3, "10"), game("KX-B", 3, "500"), game("KX-C", 4)],
                                   AUTO_RESEARCH_MAX_PER_DAY="5", MAX_CONCURRENT_RUNS="5")
    try:
        with DbSession(make_client.engine) as db:
            db.add(Run(id="old", event_ticker="KX-C", event_title="C", status="done", created_at=NOW - timedelta(hours=2)))
            db.commit()
        cycle(client)
        assert [t for t, _, _ in recorder.started] == ["KX-B", "KX-A"]  # same start time: the one with more volume first; KX-C was researched 2 h ago
    finally:
        client.__exit__(None, None, None)


def test_automatic_research_respects_the_concurrent_run_limit_and_stops_when_there_is_no_room(app_client, monkeypatch):
    client, recorder = auto_client(app_client, monkeypatch, [game("KX-A", 1), game("KX-B", 2)], AUTO_RESEARCH_MAX_PER_DAY="5", MAX_CONCURRENT_RUNS="1")
    try:
        client.app.state.active_runs = 1
        cycle(client)
        assert recorder.started == []
        client.app.state.active_runs = 0
        cycle(client)
        assert [t for t, _, _ in recorder.started] == ["KX-A"]  # only one slot
    finally:
        client.__exit__(None, None, None)


def test_without_research_configured_nothing_is_started(app_client, monkeypatch):
    client, recorder = auto_client(app_client, monkeypatch, [game("KX-A", 1)], AUTO_RESEARCH_MAX_PER_DAY="5")
    try:
        client.app.state.research_graph = None
        cycle(client)
        assert recorder.started == []
    finally:
        client.__exit__(None, None, None)


def test_the_settings_are_validated():
    base = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
    s = load_settings(base)
    assert (s.monitor_enabled, s.auto_research_max_per_day, s.alert_move_cents, s.alert_max_per_hour) == (False, 0, 8.0, 6)
    assert load_settings(base | {"AUTO_RESEARCH_MAX_PER_DAY": "0"}).auto_research_max_per_day == 0
    for bad in ({"AUTO_RESEARCH_MAX_PER_DAY": "-1"}, {"AUTO_RESEARCH_MAX_PER_DAY": "many"}, {"MONITOR_ENABLED": "yes"}, {"ALERT_MAX_PER_HOUR": "0"}, {"MONITOR_INTERVAL_MINUTES": "0"}):
        with pytest.raises(SettingsError):
            load_settings(base | bad)
