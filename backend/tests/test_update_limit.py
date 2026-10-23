"""The lineup update's foundations (FEAT-20261022-0956): the setting, two separate 24-hour limits, and the link from an update to the run it updates."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Run
from app.research.schemas import GameInfo
from app.runs import DailyLimitReached, _insert_run
from tests.conftest import alembic_config, needs_db

ENV = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
GAME = GameInfo(event_ticker="KX-1", title="A vs B", outcomes=["A wins", "B wins"], outcome_tickers=["a", "b"], exclusive=True)


def test_the_update_limit_setting_defaults_to_five_and_zero_means_no_limit():
    assert load_settings(ENV).research_updates_max_per_day == 5
    assert load_settings(ENV | {"RESEARCH_UPDATES_MAX_PER_DAY": "0"}).research_updates_max_per_day == 0
    assert load_settings(ENV | {"RESEARCH_UPDATES_MAX_PER_DAY": "12"}).research_updates_max_per_day == 12
    for bad in ("-1", "two", "1.5"):
        with pytest.raises(SettingsError, match="RESEARCH_UPDATES_MAX_PER_DAY"):
            load_settings(ENV | {"RESEARCH_UPDATES_MAX_PER_DAY": bad})


def insert(engine, run_id, event="KX-1", **kw):
    """_insert_run, then the run is marked done (a game can have only one queued or running run at a time)."""
    _insert_run(engine, run_id, GameInfo(event_ticker=event, title="A vs B", outcomes=["A wins", "B wins"], outcome_tickers=["a", "b"], exclusive=True), None, **kw)
    with DbSession(engine) as db:
        db.get(Run, run_id).status = "done"
        db.commit()


@needs_db
def test_a_run_has_a_nullable_link_to_the_run_it_updates(fresh_db):
    command.upgrade(alembic_config(), "head")
    assert "refresh_of" in {c["name"] for c in inspect(fresh_db).get_columns("runs")}
    insert(fresh_db, "r1")
    insert(fresh_db, "r2", refresh_of="r1")
    with DbSession(fresh_db) as db:
        assert db.get(Run, "r1").refresh_of is None and db.get(Run, "r2").refresh_of == "r1"


@needs_db
def test_updates_and_researched_games_have_separate_limits(fresh_db):
    command.upgrade(alembic_config(), "head")
    for i in range(2):  # two researched games fill a limit of two
        insert(fresh_db, f"g{i}", f"KX-{i}", limit=2)
    with pytest.raises(DailyLimitReached):
        insert(fresh_db, "g2", "KX-2", limit=2)
    insert(fresh_db, "u0", "KX-0", limit=2, refresh_of="g0", update_limit=1)  # an update does not use a game slot ...
    with pytest.raises(DailyLimitReached) as full:
        insert(fresh_db, "u1", "KX-0", limit=2, refresh_of="g0", update_limit=1)  # ... and has its own limit
    assert full.value.kind == "update" and full.value.used == 1
    insert(fresh_db, "u2", "KX-0", limit=2, refresh_of="g0", update_limit=0)  # 0 means no limit for updates
    with pytest.raises(DailyLimitReached) as games:  # updates never count as researched games
        insert(fresh_db, "g3", "KX-3", limit=2)
    assert games.value.kind == "game" and games.value.used == 2


@needs_db
def test_an_old_update_leaves_the_window(fresh_db):
    command.upgrade(alembic_config(), "head")
    insert(fresh_db, "g0", "KX-0")
    with DbSession(fresh_db) as db:
        db.add(Run(id="old", event_ticker="KX-9", event_title="t", status="done", refresh_of="g0", created_at=datetime.now(UTC) - timedelta(hours=25)))
        db.commit()
    insert(fresh_db, "u1", "KX-0", refresh_of="g0", update_limit=1)  # the update made 25 hours ago no longer counts


@needs_db
def test_the_dashboard_counts_researched_games_and_updates_apart(make_client):
    from tests.conftest import EMAIL, PASSWORD

    client = make_client()
    client.__enter__()
    try:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers={"X-Requested-With": "t"})
        with DbSession(make_client.engine) as db:
            for i in range(2):
                db.add(Run(id=f"g{i}", event_ticker=f"KX-{i}", event_title="t", status="done"))
            db.flush()
            db.add(Run(id="u0", event_ticker="KX-0", event_title="t", status="done", refresh_of="g0"))
            db.commit()
        spend = client.get("/api/dashboard").json()["spend"]
        assert spend["last_24h"] == 2 and spend["updates_24h"] == 1 and spend["limit"] == 5 and spend["updates_limit"] == 5
    finally:
        client.__exit__(None, None, None)
