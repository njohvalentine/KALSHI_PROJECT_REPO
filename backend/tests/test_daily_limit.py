"""The hard daily limit on researched games (RESEARCH_MAX_PER_DAY)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session as DbSession

from app.config import SettingsError, load_settings
from app.models import Run
from app.research.schemas import GameInfo
from app.runs import DailyLimitReached, _insert_run
from tests.conftest import needs_db
from tests.fakes import FakeModel
from tests.test_runs import signed_in, start, wait_done

ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}


def add_run(engine, hours_ago, status="done", ticker=None):
    with DbSession(engine) as db:
        ticker = ticker or f"OLD-{uuid.uuid4().hex[:6]}"
        db.add(Run(id=uuid.uuid4().hex, event_ticker=ticker, event_title=ticker, status=status, trigger="manual", created_at=datetime.now(UTC) - timedelta(hours=hours_ago)))
        db.commit()


def count(engine):
    with DbSession(engine) as db:
        return len(db.query(Run).all())


def test_the_limit_defaults_to_five_and_zero_means_no_limit():
    assert load_settings(ENV).research_max_per_day == 5
    assert load_settings(ENV | {"RESEARCH_MAX_PER_DAY": "0"}).research_max_per_day == 0
    assert load_settings(ENV | {"RESEARCH_MAX_PER_DAY": "12"}).research_max_per_day == 12


@pytest.mark.parametrize("bad", ["-1", "five", "2.5"])
def test_a_bad_limit_stops_the_start_with_a_clear_message(bad):
    with pytest.raises(SettingsError, match="RESEARCH_MAX_PER_DAY"):
        load_settings(ENV | {"RESEARCH_MAX_PER_DAY": bad})


@needs_db
def test_the_run_after_the_limit_is_refused_with_the_message_and_nothing_is_stored(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="2")
    try:
        for ticker in ("KX-A", "KX-B"):
            wait_done(client, start(client, ticker).json()["id"])
        refused = start(client, "KX-C")
        assert refused.status_code == 429
        detail = refused.json()["detail"]
        assert "daily research limit is reached: 2 games in the last 24 hours" in detail and "next slot opens at" in detail and "RESEARCH_MAX_PER_DAY" in detail
        assert int(refused.headers["Retry-After"]) > 0
        assert count(make_client.engine) == 2
        assert client.app.state.active_runs == 0  # the refusal gave its slot back
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_a_run_older_than_24_hours_does_not_count(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="1")
    try:
        add_run(make_client.engine, hours_ago=25)
        assert start(client, "KX-A").status_code == 202  # the old run is outside the window
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_a_failed_run_counts_and_the_message_says_when_the_slot_opens(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="1")
    try:
        add_run(make_client.engine, hours_ago=23, status="failed")
        refused = start(client, "KX-A")
        assert refused.status_code == 429
        assert "next slot opens at" in refused.json()["detail"]
        assert 3000 < int(refused.headers["Retry-After"]) <= 3601
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_zero_means_no_limit(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="0", MAX_CONCURRENT_RUNS="5")
    try:
        for i in range(4):
            add_run(make_client.engine, hours_ago=1)
        assert start(client, "KX-A").status_code == 202
    finally:
        client.__exit__(None, None, None)


@needs_db
def test_eight_starts_at_the_same_moment_take_exactly_the_free_slots(make_client):
    make_client()  # a migrated empty database
    engine = make_client.engine

    def one(i):
        try:
            _insert_run(engine, uuid.uuid4().hex, GameInfo(event_ticker=f"KX-{i}", title=f"Game {i}"), None, "manual", 3)
            return True
        except DailyLimitReached:
            return False

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(one, range(8)))
    assert sum(results) == 3 and count(engine) == 3
