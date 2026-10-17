"""Asking before paying twice for the same game."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.models import Run
from app.runs import RunStartError, start_game_run
from tests.conftest import needs_db
from tests.fakes import FakeModel
from tests.test_runs import H, signed_in, start, wait_done

pytestmark = needs_db


def add_run(engine, ticker, hours_ago, status="done", cost="0.43"):
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    with DbSession(engine) as db:
        db.add(Run(id=uuid.uuid4().hex, event_ticker=ticker, event_title=ticker, status=status, trigger="manual", created_at=when, finished_at=when, cost_usd=Decimal(cost)))
        db.commit()


def test_a_game_with_a_fresh_forecast_is_not_researched_again_until_the_person_confirms(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="0")
    try:
        add_run(make_client.engine, "KX-1", hours_ago=3)
        refused = start(client, "KX-1")
        assert refused.status_code == 409
        body = refused.json()
        assert body["code"] == "recently_researched" and body["hours_ago"] == 3.0 and body["cost_usd"] == 0.43
        assert "researched 3 hours ago for $0.43" in body["detail"] and "still fresh" in body["detail"]
        assert body["run_id"] is None  # the button must not follow it to a run
        assert client.app.state.active_runs == 0
        confirmed = client.post("/api/runs", json={"event_ticker": "KX-1", "confirm_repeat": True}, headers=H)
        assert confirmed.status_code == 202
        wait_done(client, confirmed.json()["id"])
    finally:
        client.__exit__(None, None, None)


def test_an_old_run_or_a_failed_run_does_not_trigger_the_question(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="0")
    try:
        add_run(make_client.engine, "KX-OLD", hours_ago=13)  # the forecast is no longer fresh (12 hours)
        add_run(make_client.engine, "KX-FAILED", hours_ago=1, status="failed")  # no forecast came out of it
        assert start(client, "KX-OLD").status_code == 202
        wait_done(client, start(client, "KX-FAILED").json()["id"])
    finally:
        client.__exit__(None, None, None)


def test_the_watcher_is_refused_by_the_same_guard(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="0")
    try:
        add_run(make_client.engine, "KX-1", hours_ago=2)
        try:
            asyncio.run(start_game_run(client.app, "KX-1", None, "auto"))
            raise AssertionError("the automatic start should have been refused")
        except RunStartError as refused:
            assert refused.status_code == 409 and refused.extra["code"] == "recently_researched"
    finally:
        client.__exit__(None, None, None)


def test_a_confirmed_repeat_still_meets_the_daily_limit(make_client):
    client = signed_in(make_client, FakeModel(), RESEARCH_MAX_PER_DAY="1")
    try:
        add_run(make_client.engine, "KX-1", hours_ago=2)
        again = client.post("/api/runs", json={"event_ticker": "KX-1", "confirm_repeat": True}, headers=H)
        assert again.status_code == 429 and "daily research limit" in again.json()["detail"]
    finally:
        client.__exit__(None, None, None)
