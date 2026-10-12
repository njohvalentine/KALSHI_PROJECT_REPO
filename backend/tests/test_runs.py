import time
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import text

from app.kalshi import KalshiClient
from app.research.pricing import cost_usd
from app.research.schemas import Usage
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.fakes import FakeModel

pytestmark = needs_db
H = {"X-Requested-With": "t"}


def kalshi_mock(missing=(), broken=(), no_ticker=()):
    def handler(request):
        ticker = request.url.path.rsplit("/", 1)[-1]
        if ticker in missing:
            return httpx2.Response(404)
        if ticker in broken:
            return httpx2.Response(500)
        if ticker in no_ticker:
            return httpx2.Response(200, json={"event": {}, "markets": []})
        return httpx2.Response(200, json={
            "event": {"event_ticker": ticker, "title": f"Game {ticker}", "sub_title": "Group stage"},
            "markets": [
                {"ticker": f"{ticker}-H", "title": "Home wins", "yes_sub_title": "Home", "occurrence_datetime": "2026-10-20T18:00:00Z", "rules_primary": "If Home wins ...", "yes_bid_dollars": "0.4800"},
                {"ticker": f"{ticker}-A", "title": "Away wins", "yes_sub_title": "Away", "occurrence_datetime": "2026-10-20T18:00:00Z"},
            ],
        })

    return KalshiClient("https://kalshi.test/trade-api/v2", client=httpx2.Client(transport=httpx2.MockTransport(handler)), sleep=lambda s: None)


def signed_in(make_client, model=None, kalshi=None, **env):
    client = make_client(research_model=model, **env)
    client.__enter__()
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
    client.app.state.kalshi = kalshi or kalshi_mock()
    return client


def start(client, ticker="KX-1"):
    return client.post("/api/runs", json={"event_ticker": ticker}, headers=H)


def wait_done(client, run_id, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_a_run_goes_from_start_to_a_stored_result_with_cost_and_sources(make_client):
    model = FakeModel(angle_names=["Form", "Injuries"])
    client = signed_in(make_client, model)
    try:
        r = start(client)
        assert r.status_code == 202 and r.json()["status"] == "queued"
        run = wait_done(client, r.json()["id"])
        assert run["status"] == "done" and run["error"] is None
        assert run["event_ticker"] == "KX-1" and run["event_title"] == "Game KX-1"
        assert [a["name"] for a in run["plan"]["angles"]] == ["Form", "Injuries"]
        game, _ = model.plan_calls[0]  # what the lead agent was given: the server's copy of the game
        assert (game.title, game.outcomes, game.starts_at, game.rules) == (
            "Game KX-1", ["Home wins", "Away wins"], "2026-10-20T18:00:00Z", "If Home wins ...")
        assert [f["angle"] for f in run["result"]["findings"]] == ["Form", "Injuries"]
        assert run["sourced_claims"] == 4
        planner, researcher = Usage("gpt-5.4-mini", 1000, 0, 200), Usage("gpt-5.4", 5000, 1000, 800, 2)
        assert run["input_tokens"] == 1000 + 2 * 5000 and run["output_tokens"] == 200 + 2 * 800 and run["search_calls"] == 4
        assert Decimal(run["cost_usd"]) == cost_usd(planner) + 2 * cost_usd(researcher) and run["over_budget"] is False
        assert run["started_at"] and run["finished_at"]
        with make_client.engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM source_pages WHERE run_id = :r"), {"r": run["id"]}).scalar_one() == 4
            assert conn.execute(text("SELECT count(*) FROM checkpoints WHERE thread_id = :r"), {"r": run["id"]}).scalar_one() >= 1
            assert conn.execute(text("SELECT created_by FROM runs")).scalar_one() is not None
    finally:
        client.__exit__(None, None, None)


def test_starting_needs_login_and_the_request_header(make_client):
    client = make_client(research_model=FakeModel())
    with client:
        assert client.post("/api/runs", json={"event_ticker": "KX-1"}, headers=H).status_code == 401
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        assert client.post("/api/runs", json={"event_ticker": "KX-1"}).status_code == 403
        assert client.post("/api/runs", json={"event_ticker": ""}, headers=H).status_code == 422


def test_refused_when_research_is_not_configured(make_client):
    client = signed_in(make_client, model=None)  # no key and no model
    try:
        r = start(client)
        assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_second_run_for_the_same_market_is_refused_while_one_is_active(make_client):
    client = signed_in(make_client, FakeModel(delay=0.5))
    try:
        first = start(client)
        second = start(client)
        assert first.status_code == 202
        assert second.status_code == 409 and second.json()["run_id"] == first.json()["id"]
        wait_done(client, first.json()["id"])
        assert start(client).status_code == 202  # allowed again once the first is finished
    finally:
        client.__exit__(None, None, None)


def test_too_many_runs_at_once_are_refused_and_the_slot_comes_back(make_client):
    client = signed_in(make_client, FakeModel(delay=0.5), MAX_CONCURRENT_RUNS="1")
    try:
        a = start(client, "KX-A")
        assert start(client, "KX-B").status_code == 429
        wait_done(client, a.json()["id"])
        assert start(client, "KX-B").status_code == 202
    finally:
        client.__exit__(None, None, None)


def test_kalshi_problems_are_reported_and_release_the_slot(make_client):
    client = signed_in(make_client, FakeModel(), kalshi_mock(missing={"NOPE"}, broken={"BAD"}, no_ticker={"ODD"}), MAX_CONCURRENT_RUNS="1")
    try:
        not_found = start(client, "NOPE")
        assert not_found.status_code == 404 and not_found.json()["detail"] == "Game not found"
        assert start(client, "BAD").status_code == 502
        assert start(client, "ODD").status_code == 502
        assert client.app.state.active_runs == 0  # every refusal gave its slot back
        assert start(client, "OK").status_code == 202
    finally:
        client.__exit__(None, None, None)


def test_all_researchers_failing_ends_as_failed_with_the_reasons(make_client):
    client = signed_in(make_client, FakeModel(angle_names=["A", "B"], fail={"A", "B"}))
    try:
        run = wait_done(client, start(client).json()["id"])
        assert run["status"] == "failed" and "A: Researcher call failed" in run["error"] and "B:" in run["error"]
        assert len(run["result"]["errors"]) == 2 and run["input_tokens"] == 1000  # the planner call is still counted
    finally:
        client.__exit__(None, None, None)


def test_partial_failure_is_done_with_errors_listed(make_client):
    client = signed_in(make_client, FakeModel(angle_names=["A", "B"], fail={"B"}))
    try:
        run = wait_done(client, start(client).json()["id"])
        assert run["status"] == "done" and [e["angle"] for e in run["result"]["errors"]] == ["B"]
    finally:
        client.__exit__(None, None, None)


def test_planner_crash_ends_as_failed_not_stuck(make_client):
    client = signed_in(make_client, FakeModel(angle_names=[]))  # empty plan
    try:
        run = wait_done(client, start(client).json()["id"])
        assert run["status"] == "failed" and "EmptyPlanError" in run["error"]
        assert client.app.state.active_runs == 0
    finally:
        client.__exit__(None, None, None)


def test_unknown_model_price_gives_unknown_cost_not_zero(make_client):
    client = signed_in(make_client, FakeModel(planner_usage=Usage("gpt-mystery", 100, 0, 10)))
    try:
        run = wait_done(client, start(client).json()["id"])
        assert run["status"] == "done" and run["cost_usd"] is None and "gpt-mystery" in run["cost_note"]
        assert run["over_budget"] is False
    finally:
        client.__exit__(None, None, None)


def test_a_run_over_the_cost_warning_is_flagged(make_client):
    client = signed_in(make_client, FakeModel(), RUN_COST_WARN_USD="0.001")
    try:
        assert wait_done(client, start(client).json()["id"])["over_budget"] is True
    finally:
        client.__exit__(None, None, None)


def test_runs_cut_off_by_a_restart_are_marked_failed_at_startup(make_client):
    with make_client.engine.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, event_ticker, event_title, status) VALUES ('old1', 'T1', 'Q', 'running'), ('old2', 'T2', 'Q', 'queued'), ('ok', 'T3', 'Q', 'done')"))
    client = signed_in(make_client, FakeModel())
    try:
        runs = {r["id"]: r for r in client.get("/api/runs").json()["runs"]}
        assert runs["old1"]["status"] == runs["old2"]["status"] == "failed"
        assert runs["old1"]["error"] == "Interrupted by a restart" and runs["ok"]["status"] == "done"
    finally:
        client.__exit__(None, None, None)


def test_shutting_down_mid_run_records_the_run_as_failed(make_client):
    client = signed_in(make_client, FakeModel(delay=30))
    run_id = start(client).json()["id"]
    time.sleep(0.3)
    client.__exit__(None, None, None)  # shutdown waits briefly, then cancels
    with make_client.engine.connect() as conn:
        status, error = conn.execute(text("SELECT status, error FROM runs WHERE id = :r"), {"r": run_id}).one()
    assert status == "failed" and "shutdown" in error


def test_reading_and_listing_runs(make_client):
    client = signed_in(make_client, FakeModel())
    try:
        ids = [wait_done(client, start(client, t).json()["id"])["id"] for t in ("KX-1", "KX-2")]
        assert client.get("/api/runs/nope").status_code == 404
        listing = client.get("/api/runs").json()["runs"]
        assert [r["id"] for r in listing] == ids[::-1]  # newest first
        assert "result" not in listing[0] and listing[0]["sourced_claims"] == 4  # a light summary
        assert [r["event_ticker"] for r in client.get("/api/runs?event_ticker=KX-1").json()["runs"]] == ["KX-1"]
        assert len(client.get("/api/runs?limit=1").json()["runs"]) == 1
        assert client.get("/api/runs?limit=0").status_code == 422
        latest = {r["event_ticker"]: r for r in client.get("/api/runs/latest").json()["runs"]}
        assert latest["KX-1"]["id"] == ids[0] and latest["KX-2"]["status"] == "done"
    finally:
        client.__exit__(None, None, None)
