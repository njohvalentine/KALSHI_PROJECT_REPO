"""Updates when a game's forecast or price changes (FEAT-20261022-0958): the forecast_changed and update_due alerts, the optional automatic update, the settings. Fakes only: no model, no network, no chat channel."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Alert, Run
from app.runs import RunStartError
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.test_opportunities import BASE, GOOD, GOOD_BASELINE, add_run, kalshi_for_good, outcome, prediction

H = {"X-Requested-With": "t"}
NOW = datetime.now(UTC)


def pred(home, away=None, total=0.70):
    away = 1 - home if away is None else away
    return prediction(outcome("KX-1-H", "Home wins", home, home - 0.05, home + 0.05), outcome("KX-1-A", "Away wins", away, away - 0.05, away + 0.05),
                      outcome("KXTTOTAL-1-1", "Over 1.5 goals scored", total, total - 0.05, total + 0.05, kind="total"))


def link(engine, run_id, refresh_of):
    with DbSession(engine) as db:
        db.execute(text("UPDATE runs SET refresh_of = :o WHERE id = :r"), {"o": refresh_of, "r": run_id})
        db.commit()


@pytest.fixture
def client_for(make_client):
    def build(**env):
        client = make_client(**env)
        client.__enter__()
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        client.app.state.kalshi = kalshi_for_good()
        return client
    return build


def cycle(client, now=None):
    asyncio.run(client.app.state.monitor.cycle(now or NOW))


def alerts(engine, kind=None):
    with DbSession(engine) as db:
        rows = db.query(Alert).order_by(Alert.id).all()
    return [a for a in rows if kind is None or a.kind == kind]


def two_runs(engine, old_home, new_home, update=True, new_hours_ago=1, start_in_hours=5, **kw):
    add_run(engine, "KX-1", "Home vs Away", pred(old_home), finished_hours_ago=9, run_id="run-old", baseline=GOOD_BASELINE, start_in_hours=start_in_hours)
    add_run(engine, "KX-1", "Home vs Away", pred(new_home), finished_hours_ago=new_hours_ago, run_id="run-new", baseline=GOOD_BASELINE, start_in_hours=start_in_hours, **kw)
    if update:
        link(engine, "run-new", "run-old")


# ---- the settings -------------------------------------------------------------------------------------------

def test_the_new_settings_have_their_defaults_and_reject_nonsense():
    s = load_settings(BASE)
    assert (s.alert_forecast_change_points, s.alert_update_due_minutes, s.auto_update_max_per_day) == (5.0, 90.0, 0)
    t = load_settings(BASE | {"ALERT_FORECAST_CHANGE_POINTS": "3.5", "ALERT_UPDATE_DUE_MINUTES": "120", "AUTO_UPDATE_MAX_PER_DAY": "3"})
    assert (t.alert_forecast_change_points, t.alert_update_due_minutes, t.auto_update_max_per_day) == (3.5, 120.0, 3)
    for bad in ({"ALERT_FORECAST_CHANGE_POINTS": "0"}, {"ALERT_UPDATE_DUE_MINUTES": "-5"}, {"AUTO_UPDATE_MAX_PER_DAY": "-1"}, {"AUTO_UPDATE_MAX_PER_DAY": "some"}):
        with pytest.raises(SettingsError, match=next(iter(bad))):
            load_settings(BASE | bad)


# ---- forecast_changed ---------------------------------------------------------------------------------------

@needs_db
def test_a_forecast_that_moved_five_points_makes_one_alert_with_before_and_after_and_the_verdict(client_for, make_client):
    client = client_for()
    try:
        two_runs(make_client.engine, 0.55, 0.45)
        cycle(client)
        cycle(client)  # once per run
        rows = alerts(make_client.engine, "forecast_changed")
        assert len(rows) == 1 and rows[0].run_id == "run-new"
        t = rows[0].text
        assert "Forecast changed: Home vs Away" in t and "After the lineup update" in t and "Home wins went from 55% to 45%" in t and "Away wins went from 45% to 55%" in t
        assert "Verdict: NO BET" in t and "not a recommendation" in t and "Over 1.5" not in t  # the match results are named, not the totals
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_a_repeat_run_that_is_not_an_update_says_new_run_and_a_small_change_says_nothing(client_for, make_client):
    client = client_for()
    try:
        two_runs(make_client.engine, 0.55, 0.45, update=False)
        cycle(client)
        assert "After a new run" in alerts(make_client.engine, "forecast_changed")[0].text
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_a_change_below_the_threshold_or_only_in_a_total_or_with_no_earlier_run_or_after_the_start_is_silent(client_for, make_client):
    client = client_for()
    try:
        two_runs(make_client.engine, 0.55, 0.52)  # three points
        cycle(client)
        assert alerts(make_client.engine, "forecast_changed") == []
    finally:
        client.__exit__(None, None, None)
    with DbSession(make_client.engine) as db:
        db.execute(text("DELETE FROM outcome_records")); db.execute(text("DELETE FROM runs")); db.commit()
    client = client_for()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", pred(0.55, total=0.70), finished_hours_ago=9, run_id="run-old", baseline=GOOD_BASELINE)
        add_run(make_client.engine, "KX-1", "Home vs Away", pred(0.55, total=0.40), finished_hours_ago=1, run_id="run-new", baseline=GOOD_BASELINE)  # only the total moved
        link(make_client.engine, "run-new", "run-old")
        cycle(client)
        assert alerts(make_client.engine, "forecast_changed") == []  # match results come first; they did not move
    finally:
        client.__exit__(None, None, None)
    with DbSession(make_client.engine) as db:
        db.execute(text("DELETE FROM outcome_records")); db.execute(text("DELETE FROM runs")); db.commit()
    client = client_for()
    try:
        add_run(make_client.engine, "KX-1", "Home vs Away", pred(0.55), finished_hours_ago=1, run_id="only", baseline=GOOD_BASELINE)
        cycle(client)
        assert alerts(make_client.engine, "forecast_changed") == []  # a first run has nothing to compare with
    finally:
        client.__exit__(None, None, None)
    with DbSession(make_client.engine) as db:
        db.execute(text("DELETE FROM outcome_records")); db.execute(text("DELETE FROM runs")); db.commit()
    client = client_for()
    try:
        two_runs(make_client.engine, 0.55, 0.40, start_in_hours=-1)
        cycle(client)
        assert alerts(make_client.engine, "forecast_changed") == []  # the game has started
    finally:
        client.__exit__(None, None, None)


# ---- update_due and the automatic update -----------------------------------------------------------------

def one_old_run(engine, hours_ago=9, start_in_minutes=80, run_id="run-1"):
    add_run(engine, "KX-1", "Home vs Away", GOOD, finished_hours_ago=hours_ago, run_id=run_id, baseline=GOOD_BASELINE, start_in_hours=start_in_minutes / 60)


@needs_db
def test_update_due_is_raised_in_the_window_for_an_old_forecast_even_when_it_is_stale_and_only_once(client_for, make_client):
    client = client_for()
    try:
        one_old_run(make_client.engine, hours_ago=20)  # older than OPPORTUNITY_MAX_AGE_HOURS: stale, but exactly the game that needs the update
        cycle(client)
        cycle(client)
        rows = alerts(make_client.engine, "update_due")
        assert len(rows) == 1 and rows[0].run_id == "run-1"
        assert "Lineups are probably out for Home vs Away" in rows[0].text and "starts in 80 minutes" in rows[0].text and "Update with lineups" in rows[0].text
        assert "20 hours ago" in rows[0].text and "$0.20" in rows[0].text
    finally:
        client.__exit__(None, None, None)


@needs_db
@pytest.mark.parametrize("hours_ago,start_in_minutes,update", [(9, 200, False), (2, 80, False), (9, 80, True), (9, -10, False)])
def test_update_due_is_silent_outside_the_window_for_a_young_forecast_after_an_update_and_after_the_start(client_for, make_client, hours_ago, start_in_minutes, update):
    client = client_for()
    try:
        one_old_run(make_client.engine, hours_ago=hours_ago, start_in_minutes=start_in_minutes)
        if update:
            add_run(make_client.engine, "KX-1", "Home vs Away", GOOD, finished_hours_ago=0.1, run_id="run-2", baseline=GOOD_BASELINE, start_in_hours=start_in_minutes / 60)
            link(make_client.engine, "run-2", "run-1")
        cycle(client)
        assert alerts(make_client.engine, "update_due") == []
    finally:
        client.__exit__(None, None, None)


class StartRecorder:
    def __init__(self, fail=None):
        self.started, self.fail = [], fail

    async def __call__(self, app, run_id, user_id, trigger="manual"):
        if self.fail:
            raise RunStartError(*self.fail)
        self.started.append((run_id, user_id, trigger))
        return {"id": "upd", "status": "queued"}


@pytest.fixture
def auto_update(client_for, monkeypatch):
    import app.monitor as monitor_module

    def build(**env):
        client = client_for(**env)
        client.app.state.research_graph = object()
        recorder = StartRecorder()
        monkeypatch.setattr(monitor_module, "start_update", recorder)
        return client, recorder
    return build


@needs_db
def test_the_automatic_update_is_off_by_default(auto_update, make_client):
    client, recorder = auto_update()
    try:
        one_old_run(make_client.engine)
        cycle(client)
        assert recorder.started == [] and len(alerts(make_client.engine, "update_due")) == 1  # the alert is still raised
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_the_automatic_update_starts_the_due_game_as_auto_once_per_cycle(auto_update, make_client):
    client, recorder = auto_update(AUTO_UPDATE_MAX_PER_DAY="3", MAX_CONCURRENT_RUNS="5")
    try:
        one_old_run(make_client.engine)
        cycle(client)
        assert recorder.started == [("run-1", None, "auto")]
        assert client.get("/api/alerts").json()["monitor"]["auto_update_started_today"] == 1  # the page shows it; the next cycle counts again from the runs table
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_the_automatic_update_respects_its_own_daily_cap_counts_only_automatic_updates_and_leaves_research_alone(auto_update, make_client):
    client, recorder = auto_update(AUTO_UPDATE_MAX_PER_DAY="1", MAX_CONCURRENT_RUNS="5")
    try:
        with DbSession(make_client.engine) as db:  # an automatic update already started today
            db.add(Run(id="u0", event_ticker="KX-9", event_title="t", status="done", trigger="auto", refresh_of="x", created_at=NOW - timedelta(minutes=5)))
            db.commit()
        one_old_run(make_client.engine)
        cycle(client)
        assert recorder.started == []  # the cap of one is used
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_an_automatic_update_does_not_count_as_an_automatic_research_start(auto_update, make_client):
    client, recorder = auto_update(AUTO_RESEARCH_MAX_PER_DAY="5")
    try:
        with DbSession(make_client.engine) as db:
            db.add(Run(id="u0", event_ticker="KX-9", event_title="t", status="done", trigger="auto", refresh_of="x", created_at=NOW - timedelta(minutes=5)))
            db.commit()
        cycle(client)
        assert client.get("/api/alerts").json()["monitor"]["auto_research_started_today"] == 0  # the update is not a researched game
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_the_automatic_update_stops_when_there_is_no_room_or_research_is_not_configured(auto_update, make_client):
    client, recorder = auto_update(AUTO_UPDATE_MAX_PER_DAY="3", MAX_CONCURRENT_RUNS="1")
    try:
        one_old_run(make_client.engine)
        client.app.state.active_runs = 1
        cycle(client)
        assert recorder.started == []
        client.app.state.active_runs = 0
        client.app.state.research_graph = None
        cycle(client)
        assert recorder.started == []
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_a_refused_automatic_update_is_logged_and_the_cycle_survives(auto_update, make_client):
    client, recorder = auto_update(AUTO_UPDATE_MAX_PER_DAY="3", MAX_CONCURRENT_RUNS="5")
    recorder.fail = (429, "The daily update limit is reached")
    try:
        one_old_run(make_client.engine)
        cycle(client)
        assert client.get("/api/alerts").json()["monitor"]["last_error"] is None and len(alerts(make_client.engine, "update_due")) == 1
    finally:
        client.__exit__(None, None, None)
