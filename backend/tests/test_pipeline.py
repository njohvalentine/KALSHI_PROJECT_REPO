"""The whole run, from pressing Research to the stored prediction and records, with fakes for every outside service."""

import socket
import time
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import text

from app.kalshi import KalshiClient
from app.research import pipeline, runner
from app.research.check import ClaimVerdict
from app.research.forecast import ForecastAnswer, OutcomeProbability
from app.research.pricing import cost_usd
from app.research.schemas import Usage
from tests.conftest import EMAIL, PASSWORD, needs_db
from tests.fakes import FakeModel

pytestmark = needs_db
H = {"X-Requested-With": "t"}
FACTS = ["Home beat Away 2-1 last week", "Away lost 3 of the last 5 away games"]
LINES = {"Form": [(FACTS[0], "https://form.test/a"), (FACTS[1], "https://form.test/b")]}


def kalshi_mock(price_failures_after=None):
    calls = {"event": 0}

    def handler(request):
        path = request.url.path
        if path.endswith("/milestones"):
            ev = request.url.params["related_event_ticker"]
            return httpx2.Response(200, json={"milestones": [{"start_date": "2099-10-20T16:30:00Z", "primary_event_tickers": [ev], "related_event_tickers": [ev]}]})
        if "/series/" in path:
            return httpx2.Response(200, json={"series": {"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1}})
        ticker = path.rsplit("/", 1)[-1]
        calls["event"] += 1
        if price_failures_after is not None and calls["event"] > price_failures_after:
            return httpx2.Response(500)
        return httpx2.Response(200, json={
            "event": {"event_ticker": ticker, "series_ticker": "KXT", "mutually_exclusive": True, "title": f"Game {ticker}"},
            "markets": [
                {"ticker": f"{ticker}-H", "title": "Home wins", "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.42", "yes_ask_size_fp": "200", "yes_bid_size_fp": "150"},
                {"ticker": f"{ticker}-A", "title": "Away wins", "yes_bid_dollars": "0.57", "yes_ask_dollars": "0.59", "yes_ask_size_fp": "100", "yes_bid_size_fp": "90"},
            ],
        })

    return KalshiClient("https://kalshi.test/trade-api/v2", client=httpx2.Client(transport=httpx2.MockTransport(handler)), sleep=lambda s: None)


PAGE = "<html><head><title>Report</title></head><body>" + "".join(f"<p>{f}. Reported on Monday by our staff.</p>" for f in FACTS) * 4 + "</body></html>"
FETCH = {
    "resolver": lambda host, port, type=None: [(socket.AF_INET, type, 6, "", ("93.184.216.34", port))],
    "transport": httpx2.MockTransport(lambda r: httpx2.Response(200, content=PAGE.encode(), headers={"content-type": "text/html"})),
}


class FakeJudge:
    def __init__(self, verdict="supported", error=None):
        self.verdict, self.error, self.calls = verdict, error, []

    async def judge(self, game_title, page_url, page_title, page_text, cut, claims):
        self.calls.append(page_url)
        if self.error:
            raise self.error
        quotes = list(claims) if self.verdict != "could_not_check" else []
        return [ClaimVerdict(claim_number=i, verdict=self.verdict, quotes=quotes[i - 1:i], reason="stated") for i in range(1, len(claims) + 1)], Usage("gpt-5.4-mini", 3000, 0, 100)


class FakeForecaster:
    def __init__(self, fail_without_claims=False, fail=False):
        self.fail_without_claims, self.fail, self.calls = fail_without_claims, fail, []

    async def forecast(self, game, claims, framing):
        self.calls.append((framing[0], len(claims)))
        if self.fail or (self.fail_without_claims and not claims):
            raise RuntimeError("model down")
        base = {"evidence_first": 0.62, "base_rate_first": 0.58, "devils_advocate": 0.60}[framing[0]]
        return ForecastAnswer(probabilities=[OutcomeProbability(outcome_number=1, probability=base), OutcomeProbability(outcome_number=2, probability=1 - base)],
                              reasoning=f"{framing[0]} reasoning"), Usage("gpt-5.4", 2000, 0, 1000)


def signed_in(make_client, judge=None, forecaster=None, kalshi=None, model=None, fetch_options=None, **env):
    client = make_client(research_model=model or FakeModel(angle_names=["Form"], lines=LINES), judge=judge or FakeJudge(),
                         forecaster=forecaster or FakeForecaster(), fetch_options=fetch_options or FETCH, **env)
    client.__enter__()
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
    client.app.state.kalshi = kalshi or kalshi_mock()
    return client


def run_game(client, ticker="KX-1"):
    run_id = client.post("/api/runs", json={"event_ticker": ticker}, headers=H).json()["id"]
    end = time.time() + 20
    while time.time() < end:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def count(make_client, table, run_id):
    with make_client.engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table} WHERE run_id = :r"), {"r": run_id}).scalar_one()


def test_a_run_goes_through_every_stage_and_stores_everything(make_client, monkeypatch):
    seen = []
    real = runner._update
    monkeypatch.setattr(runner, "_update", lambda engine, run_id, **kw: (seen.append(kw["stage"]) if "stage" in kw else None, real(engine, run_id, **kw))[1])
    client = signed_in(make_client)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["error"] is None and run["stage"] == "done"
    assert seen == ["research", "fetch", "check", "forecast", "compare"]

    assert [p["fetch_status"] for p in run["pages"]] == ["ok", "ok"] and "page_text" not in str(run)
    assert [c["verdict"] for c in run["claim_checks"]] == ["supported", "supported"]
    assert len(run["forecasts"]) == 3 * 2 and {f["variant"] for f in run["forecasts"]} == {"evidence_first", "base_rate_first", "devils_advocate"}

    p = run["prediction"]
    assert p["forecasters_valid"] == 3 and p["evidence"] == "supported" and p["supported_claims"] == 2 and "unavailable" not in p
    home = next(o for o in p["outcomes"] if o["market_ticker"] == "KX-1-H")
    assert home["probability"] == pytest.approx(0.60, abs=0.001) and home["spread"] == pytest.approx(0.04, abs=0.001)
    assert p["pipeline"] == {"pages": {"ok": 2}, "claim_checks": {"supported": 2}, "baseline": True}
    comparison = p["comparison"]
    assert comparison["fee"]["source"] == "series" and comparison["outcomes"][0]["yes_ask"] == 0.42
    assert comparison["outcomes"][0]["meaningful"] is False  # only 2 supported claims, MIN_SUPPORTED_CLAIMS is 5
    assert any("only 2 supported claims" in r for r in comparison["outcomes"][0]["reasons"])

    assert count(make_client, "forecasts", run["id"]) == 6 and count(make_client, "claim_checks", run["id"]) == 2
    with make_client.engine.connect() as conn:
        rows = conn.execute(text("SELECT market_ticker, probability, baseline_probability, before_start, yes_ask, resolved_at FROM outcome_records ORDER BY market_ticker")).all()
    assert [r[0] for r in rows] == ["KX-1-A", "KX-1-H"] and rows[1][3] is True and rows[1][4] == Decimal("0.42") and rows[1][5] is None
    assert rows[1][2] == Decimal("0.62")  # the baseline is the first framing's answer with no facts

    research = Usage("gpt-5.4-mini", 1000, 0, 200)  # planner; the two researchers follow
    researcher = Usage("gpt-5.4", 5000, 1000, 800, 2)
    check, forecast, baseline = Usage("gpt-5.4-mini", 3000, 0, 100), Usage("gpt-5.4", 2000, 0, 1000), Usage("gpt-5.4", 2000, 0, 1000)
    expected = {"research": cost_usd(research) + cost_usd(researcher), "check": 2 * cost_usd(check),
                "forecast": 3 * cost_usd(forecast), "baseline": cost_usd(baseline)}
    assert {k: Decimal(v) for k, v in run["costs"].items()} == expected
    assert Decimal(run["cost_usd"]) == sum(expected.values()) and run["input_tokens"] == 1000 + 5000 + 2 * 3000 + 3 * 2000 + 2000


def test_supported_odds_claims_are_never_given_to_the_forecasters(make_client):
    lines = {"Form": [(FACTS[0], "https://form.test/a")], "Prices": [("Arsenal 2.10, Draw 3.40, Lille 3.60 at one bookmaker", "https://book.test/a")]}
    model = FakeModel(angle_names=["Form", "Prices"], lines=lines)
    forecaster = FakeForecaster()
    odds_page = PAGE.replace("</body>", "<p>Arsenal 2.10, Draw 3.40, Lille 3.60 at one bookmaker. " * 12 + "</p></body>")
    fetch = FETCH | {"transport": httpx2.MockTransport(lambda r: httpx2.Response(200, content=odds_page.encode(), headers={"content-type": "text/html"}))}
    client = signed_in(make_client, model=model, forecaster=forecaster, judge=FakeJudge(), fetch_options=fetch)
    # the fake planner returns plain angles; mark the second one as market information the way the real planner does
    real_plan = model.plan

    async def plan(game, max_angles):
        plan_, usage = await real_plan(game, max_angles)
        plan_.angles[1].kind = "market_odds"
        return plan_, usage
    model.plan = plan
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert [c["verdict"] for c in run["claim_checks"]] == ["supported", "supported"]  # both were checked and are shown, and the odds claim IS supported
    assert run["prediction"]["supported_claims"] == 1  # but only the form claim goes forward
    assert {n for _, n in forecaster.calls if n} == {1}  # three forecasters saw one fact each (the baseline saw none)


def test_the_run_returns_the_baseline_and_the_latest_call_a_compact_forecast_without_text(make_client):
    client = signed_in(make_client)
    try:
        run = run_game(client)
        latest = client.get("/api/runs/latest").json()["runs"][0]
    finally:
        client.__exit__(None, None, None)
    assert run["baseline"] == {"KX-1-H": 0.62, "KX-1-A": 0.38}
    assert latest["event_ticker"] == "KX-1" and latest["status"] == "done"
    forecast = latest["forecast"]
    assert [o["market_ticker"] for o in forecast["outcomes"]] == ["KX-1-H", "KX-1-A"] and forecast["outcomes"][0]["probability"] == pytest.approx(0.6, abs=0.001)
    assert all(o["flagged"] is False for o in forecast["outcomes"]) and forecast["forecast_at"]
    assert "reasoning" not in str(latest) and "page_text" not in str(latest)


def test_no_forecast_and_no_baseline_when_there_is_no_prediction(make_client):
    client = make_client(research_model=FakeModel(angle_names=["Form"], lines=LINES))  # no judge or forecaster
    client.__enter__()
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
    client.app.state.kalshi = kalshi_mock()
    try:
        run = run_game(client)
        latest = client.get("/api/runs/latest").json()["runs"][0]
    finally:
        client.__exit__(None, None, None)
    assert run["baseline"] is None and latest["forecast"] is None


def test_the_run_list_shows_the_stage_and_how_many_outcomes_were_flagged(make_client):
    client = signed_in(make_client, model=FakeModel(angle_names=["Form"], lines={"Form": [(f"Fact {i} is 1-0", f"https://form.test/{i}") for i in range(6)]}),
                       judge=FakeJudge())
    try:
        run_game(client)
        listed = client.get("/api/runs").json()["runs"][0]
    finally:
        client.__exit__(None, None, None)
    assert listed["stage"] == "done" and listed["flagged_outcomes"] in (0, 1, 2) and "prediction" not in listed


def test_fetch_failing_keeps_the_research_and_says_which_stage_failed(make_client, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(pipeline, "fetch_run_sources", boom)
    client = signed_in(make_client)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["prediction"] == {"unavailable": "fetch failed: OSError"}
    assert len(run["result"]["findings"]) == 1 and count(make_client, "outcome_records", run["id"]) == 0 and count(make_client, "forecasts", run["id"]) == 0


def test_error_text_stays_in_the_log_and_out_of_the_run(make_client, monkeypatch, caplog):
    secret = "password=hunter2 host=10.0.0.5 sk-proj-abc123"

    def boom(*a, **k):
        raise OSError(secret)
    monkeypatch.setattr(pipeline, "fetch_run_sources", boom)
    client = signed_in(make_client)
    try:
        with caplog.at_level("ERROR"):
            run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert secret not in str(run) and run["prediction"] == {"unavailable": "fetch failed: OSError"}
    assert secret in caplog.text  # the operator can still see it


def test_an_unexpected_failure_of_the_whole_run_shows_only_the_error_kind(make_client, monkeypatch, caplog):
    secret = "connection to server at 10.0.0.5 failed, password=hunter2"

    def boom(*a, **k):
        raise RuntimeError(secret)
    monkeypatch.setattr(runner, "summarize", boom)
    client = signed_in(make_client)
    try:
        with caplog.at_level("ERROR"):
            run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "failed" and run["error"] == "RuntimeError (details are in the server log)"
    assert secret not in str(run) and secret in caplog.text


def test_the_check_stage_failing_is_named(make_client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(pipeline, "check_run", boom)
    client = signed_in(make_client)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["prediction"] == {"unavailable": "check failed: RuntimeError"}


def test_all_forecasters_failing_gives_no_prediction_and_no_records(make_client):
    client = signed_in(make_client, forecaster=FakeForecaster(fail=True))
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and "Only 0 valid forecast(s)" in run["prediction"]["unavailable"]
    assert run["prediction"]["dropped"][0]["reason"] == "call failed: RuntimeError" and count(make_client, "outcome_records", run["id"]) == 0


@pytest.mark.parametrize("env", [{"CHECK_ENABLED": "false"}, {"FETCH_ENABLED": "false"}])
def test_switching_checking_off_stops_after_research_and_says_so(make_client, env):
    judge = FakeJudge()
    client = signed_in(make_client, judge=judge, **env)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["prediction"] == {"unavailable": pipeline.SWITCHED_OFF} and judge.calls == []
    assert [p["fetch_status"] for p in run["pages"]] == ["not_fetched", "not_fetched"]


def test_without_a_judge_or_forecaster_the_run_says_it_is_not_configured(make_client):
    client = make_client(research_model=FakeModel(angle_names=["Form"], lines=LINES))
    client.__enter__()
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
    client.app.state.kalshi = kalshi_mock()
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["prediction"] == {"unavailable": pipeline.NOT_CONFIGURED}


def test_no_supported_claims_still_forecasts_from_the_base_rate_and_never_flags(make_client):
    forecaster = FakeForecaster()
    client = signed_in(make_client, judge=FakeJudge("could_not_check"), forecaster=forecaster)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    p = run["prediction"]
    assert p["evidence"] == "none" and p["supported_claims"] == 0 and p["forecasters_valid"] == 3
    assert all(n == 0 for _, n in forecaster.calls)  # every forecaster, and the baseline, saw no facts
    assert all(not o["meaningful"] for o in p["comparison"]["outcomes"])
    assert any("no supported evidence" in r for r in p["comparison"]["outcomes"][0]["reasons"])
    assert count(make_client, "outcome_records", run["id"]) == 2


def test_unreadable_prices_keep_the_prediction_and_record_without_a_market_snapshot(make_client):
    client = signed_in(make_client, kalshi=kalshi_mock(price_failures_after=1))  # the start of the run reads the game once
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and "Kalshi prices could not be read" in run["prediction"]["comparison"]["unavailable"]
    with make_client.engine.connect() as conn:
        rows = conn.execute(text("SELECT yes_ask, side, reasons FROM outcome_records")).all()
    assert len(rows) == 2 and all(r[0] is None and r[1] is None and "no market snapshot" in r[2][0] for r in rows)


def test_a_failed_baseline_is_left_empty_and_the_rest_is_kept(make_client):
    client = signed_in(make_client, forecaster=FakeForecaster(fail_without_claims=True), judge=FakeJudge())
    try:
        # with supported claims the forecasters work; the baseline (no facts) is the call that fails
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and run["prediction"]["pipeline"]["baseline"] is False and run["prediction"]["forecasters_valid"] == 3
    with make_client.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM outcome_records WHERE baseline_probability IS NULL")).scalar_one() == 2
    assert "baseline" not in run["costs"]


def test_the_cost_warning_uses_the_total_of_all_stages(make_client):
    research = cost_usd(Usage("gpt-5.4-mini", 1000, 0, 200)) + cost_usd(Usage("gpt-5.4", 5000, 1000, 800, 2))
    client = signed_in(make_client, RUN_COST_WARN_USD=str(float(research) + 0.0001))  # research alone is below it, the total is above
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["over_budget"] is True
