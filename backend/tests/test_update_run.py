"""A lineup update of a researched game, from the button to the stored forecast, with fakes for every outside service (FEAT-20261022-0956)."""

import time
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app import runs as runs_module
from app.models import Run
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.fakes import FakeModel
from tests.test_pipeline import FACTS, FETCH, FakeForecaster, FakeJudge, count, kalshi_mock, signed_in as pipeline_signed_in

pytestmark = needs_db
H = {"X-Requested-With": "t"}
NEW_FACT = "Away captain is out with a hamstring injury"
NEW_LINES = [(NEW_FACT, "https://late.test/a")]
PAGE = "<html><head><title>Report</title></head><body>" + "".join(f"<p>{f}. Reported on Monday by our staff.</p>" for f in FACTS + [NEW_FACT]) * 4 + "</body></html>"
FETCH_ALL = {"resolver": FETCH["resolver"], "transport": httpx2.MockTransport(lambda r: httpx2.Response(200, content=PAGE.encode(), headers={"content-type": "text/html"}))}


class UpdateModel(FakeModel):
    """Plans one angle for a normal run; for an update it must be asked only to research the fixed angle."""

    def __init__(self):
        super().__init__(angle_names=["Form"], lines={"Form": [(FACTS[0], "https://form.test/a"), (FACTS[1], "https://form.test/b")], "Late team news": NEW_LINES}, delay=0)


def signed_in(make_client, judge=None, forecaster=None, model=None, **env):
    return pipeline_signed_in(make_client, judge=judge or FakeJudge(), forecaster=forecaster or FakeForecaster(), model=model or UpdateModel(), fetch_options=FETCH_ALL, **env)


def wait(client, run_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def researched(client, ticker="KX-1"):
    return wait(client, client.post("/api/runs", json={"event_ticker": ticker}, headers=H).json()["id"])


def update(client, run_id):
    return client.post(f"/api/runs/{run_id}/update", headers=H)


def test_an_update_researches_only_the_fixed_angle_reuses_the_earlier_evidence_and_links_to_the_earlier_run(make_client):
    model, judge, forecaster = UpdateModel(), FakeJudge(), FakeForecaster()
    client = signed_in(make_client, judge=judge, forecaster=forecaster, model=model)
    try:
        first = researched(client)
        assert first["status"] == "done" and first["update"]["allowed"] is True and first["refresh_of"] is None
        judged_before, forecaster_before = len(judge.calls), len(forecaster.calls)
        started = update(client, first["id"])
        assert started.status_code == 202
        second = wait(client, started.json()["id"])
        assert second["status"] == "done" and second["refresh_of"] == first["id"]
        assert len(model.plan_calls) == 1 and model.research_calls == ["Form", "Late team news"]  # the planner ran for the first run only
        findings = second["result"]["findings"]
        assert findings[0]["angle"] == "Late team news" and findings[1]["angle"].startswith("Earlier research (") and findings[1]["carried_from"] == first["id"]
        assert set(judge.calls[judged_before:]) == {"https://late.test/a"}  # only the new page was judged; the carried pages were not
        assert [c["verdict"] for c in second["claim_checks"] if c["finding_index"] == 0] == ["supported"]
        assert sum(1 for c in second["claim_checks"] if c["finding_index"] > 0) == 2 and {p["url"] for p in second["pages"]} == {"https://late.test/a", "https://form.test/a", "https://form.test/b"}
        assert len(forecaster.calls) - forecaster_before == 3 + 1 and forecaster.calls[-1][1] == 3  # three forecasters (and the plain AI call), the facts: 1 new + 2 earlier
        assert second["prediction"]["supported_claims"] == 3 and second["cost_usd"] is not None and float(second["cost_usd"]) < float(first["cost_usd"])  # no planner call, one researcher
        assert count(make_client, "outcome_records", second["id"]) == 2 and count(make_client, "outcome_records", first["id"]) == 2  # both forecasts stay on file
        assert second["previous"]["run_id"] == first["id"] and set(second["previous"]["probabilities"]) == {"KX-1-H", "KX-1-A"}
        assert client.get(f"/api/runs/{first['id']}").json()["update"]["reason"] == "A newer run of this game exists: update that one."
        assert wait(client, first["id"])["update"]["allowed"] is False  # the earlier run can no longer be updated, the newest can
        assert second["update"]["allowed"] is True
    finally:
        client.__exit__(None, None, None)


def test_an_update_needs_login_and_the_guard_header_and_a_finished_run_that_exists(make_client):
    client = signed_in(make_client)
    try:
        first = researched(client)
        assert client.post(f"/api/runs/{first['id']}/update").status_code == 403  # no X-Requested-With header
        assert update(client, "no-such-run").status_code == 404
        client.post("/auth/logout", headers=H)
        assert update(client, first["id"]).status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_the_refusals_say_why(make_client, monkeypatch):
    client = signed_in(make_client)
    try:
        first = researched(client)
        # not the newest run of the game
        engine = make_client.engine
        with DbSession(engine) as db:
            db.add(Run(id="newer", event_ticker="KX-1", event_title="t", status="done", prediction={"outcomes": []}, created_at=datetime.now(UTC) + timedelta(seconds=5)))
            db.commit()
        refused = update(client, first["id"])
        assert refused.status_code == 409 and "newer run" in refused.json()["detail"] and refused.json()["code"] == "not_updatable"
        with DbSession(engine) as db:
            db.delete(db.get(Run, "newer"))
            db.add(Run(id="busy", event_ticker="KX-1", event_title="t", status="running", created_at=datetime.now(UTC) + timedelta(seconds=5)))
            db.commit()
        assert update(client, first["id"]).status_code == 409  # a run of this game is in progress
        with DbSession(engine) as db:
            db.delete(db.get(Run, "busy"))
            db.commit()
        # the game has started (Kalshi's start time is in the past)
        monkeypatch.setattr(runs_module, "_kickoff", lambda kalshi, ticker: (datetime.now(UTC) - timedelta(hours=1)).isoformat())
        started = update(client, first["id"])
        assert started.status_code == 409 and "started" in started.json()["detail"]
        monkeypatch.undo()
        # a run without a forecast
        with DbSession(engine) as db:
            db.add(Run(id="nofc", event_ticker="KX-9", event_title="t", status="failed"))
            db.commit()
        assert update(client, "nofc").status_code == 409
        # no OpenAI configured
        client.app.state.research_graph = None
        assert update(client, first["id"]).status_code == 503
    finally:
        client.__exit__(None, None, None)


def test_the_update_limit_is_separate_from_the_game_limit(make_client):
    client = signed_in(make_client, RESEARCH_MAX_PER_DAY="1", RESEARCH_UPDATES_MAX_PER_DAY="1")
    try:
        first = researched(client)
        second = wait(client, update(client, first["id"]).json()["id"])  # the game used the only game slot; the update has its own slot
        assert second["status"] == "done"
        refused = update(client, second["id"])
        assert refused.status_code == 429 and "update limit" in refused.json()["detail"] and "RESEARCH_UPDATES_MAX_PER_DAY" in refused.json()["detail"] and "Retry-After" in refused.headers
        again = client.post("/api/runs", json={"event_ticker": "KX-2"}, headers=H)
        assert again.status_code == 429 and "research limit" in again.json()["detail"]  # and the update did not open a game slot
        assert client.app.state.active_runs == 0
    finally:
        client.__exit__(None, None, None)
