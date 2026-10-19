"""The price-only test on Kalshi's history: sampling, the price an hour before the start, the strategies, the strict interval and the rule. No network."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app import cli
from app.kalshi import KalshiClient
from app.research.compare import FeeInfo
from app.research.pricetest import (Cache, Game, Outcome, analyse, bootstrap, calibration, collect, format_report, game_results, horizon_label, information_arrival,
                                    pick_price, run, sample_events, verdict)

FEE = FeeInfo("quadratic", Decimal(1), "series")
D = Decimal


def candle(end, bid=None, ask=None, live=False):
    key = "close_dollars" if live else "close"
    return {"end_period_ts": end, "yes_bid": {key: bid} if bid is not None else {}, "yes_ask": {key: ask} if ask is not None else {}}


def test_the_price_is_the_last_candle_ending_at_least_an_hour_before_the_start_with_a_bid_and_an_ask():
    start = 100_000
    candles = [candle(start - 7200, "0.40", "0.42"), candle(start - 3600, "0.44", "0.46"), candle(start - 1800, "0.50", "0.52"), candle(start - 3600 - 3600, None, None)]
    assert pick_price(candles, start) == (D("0.44"), D("0.46"))  # the one ending exactly an hour before; the later ones are too close to the start
    assert pick_price([candle(start - 3600, None, "0.46"), candle(start - 7200, "0.40", "0.42")], start) == (D("0.40"), D("0.42"))  # a candle without a bid is skipped
    assert pick_price([candle(start - 3600, "0.44", "0.46", live=True)], start) == (D("0.44"), D("0.46"))  # the normal tier names the field differently
    assert pick_price([candle(start - 600, "0.5", "0.52")], start) is None


def markets(n, series="S"):
    out = []
    for i in range(n):  # n games of two markets each, settled in order, the first market always the winner
        out += [{"ticker": f"{series}-{i:03d}-A", "event": f"{series}-{i:03d}", "result": "yes", "close": f"2026-01-{i % 28 + 1:02d}T{i // 28:02d}:00:00Z"},
                {"ticker": f"{series}-{i:03d}-B", "event": f"{series}-{i:03d}", "result": "no", "close": f"2026-01-{i % 28 + 1:02d}T{i // 28:02d}:00:00Z"}]
    return out


def test_the_sample_is_every_kth_game_in_order_of_settlement_and_never_more_than_the_limit():
    events, dropped = sample_events(markets(1000), sample=400)
    assert len(events) <= 400 and len(events) > 300 and not dropped
    assert events == sorted(events, key=lambda e: next(m["close"] for m in markets(1000) if m["event"] == e))  # in order of settlement
    assert events[0] == "S-000" and events[1] != "S-001"  # spread out, not the first 400
    small, _ = sample_events(markets(10), sample=400)
    assert len(small) == 10  # fewer games than the limit: all of them


def test_games_without_a_single_winner_or_with_an_unusual_structure_are_dropped_with_the_reason():
    ms = markets(3) + [{"ticker": "V-A", "event": "V", "result": "no", "close": "x"}, {"ticker": "V-B", "event": "V", "result": "no", "close": "x"},  # voided
                       {"ticker": "U-A", "event": "U", "result": "yes", "close": "x"}, {"ticker": "U-B", "event": "U", "result": "no", "close": "x"},
                       {"ticker": "U-C", "event": "U", "result": "no", "close": "x"}, {"ticker": "U-D", "event": "U", "result": "no", "close": "x"},
                       {"ticker": "N-A", "event": "N", "result": None, "close": "x"}, {"ticker": "N-B", "event": "N", "result": None, "close": "x"}]
    events, dropped = sample_events(ms)
    assert sorted(events) == ["S-000", "S-001", "S-002"]
    assert dropped == Counter({"no single winner (voided or unfinished)": 2, "unusual market structure": 1})


def game(event, a_bid, a_ask, b_bid, b_ask, a_won, day=1, series="KXEPLGAME"):
    return Game(event, series, datetime(2026, 3, day, 15, tzinfo=UTC),
                [Outcome(event + "-A", D(a_bid), D(a_ask), a_won), Outcome(event + "-B", D(b_bid), D(b_ask), not a_won)])


def test_the_three_strategies_on_games_with_known_results():
    close = game("G1", "0.50", "0.52", "0.47", "0.49", True)  # a favourite that won, no longshot
    fav, longshot_no, longshot_yes = game_results(close, FEE)["F"], game_results(close, FEE)["L"], game_results(close, FEE)["N"]
    assert fav == (D("1") - D("0.52") - D("0.07") * D("0.52") * D("0.48"), 1) and longshot_no == (D(0), 0) and longshot_yes == (D(0), 0)
    lopsided = game("G2", "0.89", "0.91", "0.08", "0.10", True)  # the longshot lost
    r = game_results(lopsided, FEE)
    assert r["F"][1] == 1 and r["F"][0] == D("1") - D("0.91") - D("0.07") * D("0.91") * D("0.09")
    assert r["L"] == (-(D("0.10") + D("0.07") * D("0.10") * D("0.90")), 1)  # bought yes at 10 cents and lost
    no_ask = D("1") - D("0.08")
    assert r["N"] == (D("1") - (no_ask + D("0.07") * no_ask * (D("1") - no_ask)), 1)  # bought no at 92 cents and won


def test_the_interval_resamples_whole_games_and_is_reproducible():
    one_big_game = [(D(100), 100), (D(-1), 1)]  # 100 bets of +1 in one game, and one bet of -1 in another
    b = bootstrap(one_big_game)
    assert abs(b["mean"] - 99 / 101) < 1e-9
    assert b["ci99"][0] < 0  # whole games are resampled: a sample made of the small game alone gives -1 (resampling bets would hide this)
    assert bootstrap(one_big_game) == b  # the seed makes it reproducible
    wide, narrow = bootstrap([(D(i % 3 - 1), 1) for i in range(30)]), bootstrap([(D(i % 3 - 1), 1) for i in range(300)])
    assert wide["ci99"][1] - wide["ci99"][0] > narrow["ci99"][1] - narrow["ci99"][0]
    assert bootstrap([(D("0.05"), 1)] * 40)["ci99"] == (pytest.approx(0.05), pytest.approx(0.05))
    assert bootstrap([])["mean"] is None


def h(mean, low=None):
    return {"bets": 100, "mean": mean, "ci99": None if low is None else (low, low + 0.1)}


def test_the_rule_found_not_confirmed_no_pattern():
    assert verdict(h(0.02), h(0.03, 0.01)) == "FOUND"
    assert verdict(h(0.02), h(0.03, -0.01)) == "not confirmed"  # the second half is positive but its 99% interval reaches zero
    assert verdict(h(0.04), h(-0.01, -0.05)) == "not confirmed"  # looked good in the first half only
    assert verdict(h(-0.02), h(0.03, 0.01)) == "no pattern"  # the halves disagree in sign: not found
    assert verdict(h(None), h(0.03, 0.01)) == "too few bets"


def test_the_groups_the_halves_by_date_and_the_calibration():
    fees = {"KXEPLGAME": FEE, "KXATPMATCH": FEE}
    games = [game(f"E{i}", "0.50", "0.52", "0.47", "0.49", i % 2 == 0, day=i + 1) for i in range(10)] + [game("T1", "0.60", "0.62", "0.37", "0.39", True, 20, "KXATPMATCH")]
    result = analyse(games, fees)
    assert set(result) == {"All", "Premier League", "Soccer (all)", "ATP", "Tennis (all)"} and result["All"]["games"] == 11
    assert result["Premier League"]["strategies"]["F"]["first"]["bets"] == 5 and result["Premier League"]["strategies"]["F"]["second"]["bets"] == 5
    assert result["Premier League"]["from"] == "2026-03-01" and result["Premier League"]["to"] == "2026-03-10"
    cal = calibration(games)
    assert [r["bucket"] for r in cal] == ["30-40¢", "40-50¢", "50-60¢", "60-70¢"] and sum(r["n"] for r in cal) == 22
    assert "Kalshi price test" in format_report(result, Counter({"x: no start time": 2}), 11) and "x: no start time: 2" in format_report(result, Counter({"x: no start time": 2}), 11)


class FakeKalshi:
    """The history endpoints for one series of three games; counts the requests."""

    def __init__(self):
        self.requests = []
        self.client = KalshiClient("https://k.test/trade-api/v2", client=httpx2.Client(transport=httpx2.MockTransport(self.handle)), sleep=lambda s: None)

    def handle(self, request):
        path = request.url.path.removeprefix("/trade-api/v2")
        self.requests.append(path)
        if path.startswith("/series/"):
            return httpx2.Response(200, json={"series": {"fee_type": "quadratic", "fee_multiplier": 1}})
        if path == "/historical/markets":
            assert request.url.params["series_ticker"] == "KXEPLGAME"
            opened = {0: "2026-02-10T00:00:00Z", 1: "2026-03-01T00:00:00Z", 2: "2026-02-10T00:00:00Z"}  # G1's markets opened only a day before its start
            ms = [{"ticker": f"KXEPLGAME-G{i}-{s}", "event_ticker": f"KXEPLGAME-G{i}", "result": "yes" if s == "A" else "no", "close_time": f"2026-03-0{i + 1}T20:00:00Z",
                   "open_time": opened[i]} for i in range(3) for s in "AB"]
            return httpx2.Response(200, json={"markets": ms, "cursor": ""})
        if path == "/milestones":
            ev = request.url.params["related_event_ticker"]
            if ev.endswith("G2"):
                return httpx2.Response(200, json={"milestones": []})  # no start time for this game
            day = int(ev[-1]) + 1
            return httpx2.Response(200, json={"milestones": [{"start_date": f"2026-03-0{day}T15:00:00Z", "primary_event_tickers": [ev], "related_event_tickers": []}]})
        if path.endswith("/candlesticks"):
            ticker = path.split("/")[-2]
            start = int(datetime(2026, 3, int(ticker.split("-")[1][1]) + 1, 15, tzinfo=UTC).timestamp())
            bid, ask = ("0.50", "0.52") if ticker.endswith("A") else ("0.47", "0.49")
            if "G1" in ticker and ticker.endswith("B"):
                bid, ask = "0.30", "0.60"  # a spread of 30 cents: the game is dropped
            return httpx2.Response(200, json={"candlesticks": [candle(int(request.url.params["end_ts"]), bid, ask)]})  # the last candle of the window asked for
        raise AssertionError(path)


def test_collect_keeps_usable_games_drops_the_rest_with_reasons_and_a_second_run_downloads_nothing(tmp_path):
    fake = FakeKalshi()
    games, dropped, fees = collect(fake.client, Cache(tmp_path), ["KXEPLGAME"], pause=0)
    assert [g.event for g in games] == ["KXEPLGAME-G0"] and games[0].outcomes[0].won is True and games[0].outcomes[0].bid == D("0.50")
    assert dropped == Counter({"KXEPLGAME: no start time": 1, "KXEPLGAME: spread wider than 10 cents": 1}) and fees["KXEPLGAME"].multiplier == 1
    first_run = len(fake.requests)
    assert first_run > 0 and not any(r.endswith("/cutoff") for r in fake.requests)
    collect(fake.client, Cache(tmp_path), ["KXEPLGAME"], pause=0)
    assert len(fake.requests) == first_run  # everything came from the cache


def test_run_returns_the_report_and_refuses_when_no_game_is_usable(tmp_path):
    report = run(FakeKalshi().client, tmp_path, ["KXEPLGAME"], log_line=lambda s: None)
    assert "Kalshi price test" in report and "Games dropped, and why" in report
    empty = FakeKalshi()
    empty.handle = lambda request: httpx2.Response(200, json={"series": {}} if "/series/" in request.url.path else {"markets": [], "cursor": ""})
    empty.client = KalshiClient("https://k.test/trade-api/v2", client=httpx2.Client(transport=httpx2.MockTransport(empty.handle)), sleep=lambda s: None)
    with pytest.raises(SystemExit, match="no game could be used"):
        run(empty.client, None, ["KXEPLGAME"], log_line=lambda s: None)


def test_the_command_refuses_an_unknown_series(monkeypatch, capsys):
    for k, v in {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}.items():
        monkeypatch.setenv(k, v)
    assert cli.main(["price-test", "--series", "KXNOPE"]) == 2
    assert "unknown series KXNOPE" in capsys.readouterr().err


def test_an_overloaded_kalshi_is_waited_for_and_a_game_is_dropped_only_after_all_the_tries(tmp_path, monkeypatch):
    monkeypatch.setattr("app.research.pricetest.time.sleep", lambda s: None)
    fake = FakeKalshi()
    real, failures = fake.handle, {"n": 0}

    def flaky(request):
        if request.url.path.endswith("/candlesticks") and failures["n"] < 7:  # the client's own 3 tries fail twice over, then it answers
            failures["n"] += 1
            return httpx2.Response(429)
        return real(request)

    fake.client = KalshiClient("https://k.test/trade-api/v2", client=httpx2.Client(transport=httpx2.MockTransport(flaky)), sleep=lambda s: None)
    games, dropped, _ = collect(fake.client, Cache(tmp_path), ["KXEPLGAME"], pause=0, workers=1)
    assert [g.event for g in games] == ["KXEPLGAME-G0"] and "KXEPLGAME: Kalshi could not be read after repeated tries" not in dropped  # it waited and got through

    always = KalshiClient("https://k.test/trade-api/v2", sleep=lambda s: None, client=httpx2.Client(transport=httpx2.MockTransport(
        lambda r: httpx2.Response(429) if r.url.path.endswith("/candlesticks") else real(r))))
    games, dropped, _ = collect(always, Cache(None), ["KXEPLGAME"], pause=0, workers=1)
    assert games == [] and dropped["KXEPLGAME: Kalshi could not be read after repeated tries"] == 2  # the games that had a start time, said plainly


DAY = 86400


def test_the_price_is_chosen_at_the_requested_lead_and_the_labels_read_plainly():
    start = 10_000_000
    candles = [candle(start - 14 * DAY, "0.40", "0.44"), candle(start - 7 * DAY, "0.45", "0.49"), candle(start - 6 * DAY, "0.50", "0.52"), candle(start - 3600, "0.60", "0.62")]
    assert pick_price(candles, start, 14 * DAY) == (D("0.40"), D("0.44"))
    assert pick_price(candles, start, 7 * DAY) == (D("0.45"), D("0.49"))  # the later candles are too close to the start
    assert pick_price(candles, start) == (D("0.60"), D("0.62"))  # the default is one hour
    assert [horizon_label(h) for h in (1, 24, 72, 168, 336, 30)] == ["1 hour", "24 hours", "3 days", "7 days", "14 days", "30 hours"]


def candle_requests(fake):
    return [r for r in fake.requests if r.endswith("/candlesticks")]


def test_each_horizon_has_its_own_candles_and_a_market_not_yet_open_costs_no_request(tmp_path):
    fake = FakeKalshi()
    cache = Cache(tmp_path)
    one_hour, d1, _ = collect(fake.client, cache, ["KXEPLGAME"], pause=0)
    after_one_hour = len(candle_requests(fake))
    assert [g.event for g in one_hour] == ["KXEPLGAME-G0"] and after_one_hour == 4  # G0 (2 markets) and G1 (2 markets)
    week, dropped, _ = collect(fake.client, cache, ["KXEPLGAME"], pause=0, lead_hours=168)
    assert [g.event for g in week] == ["KXEPLGAME-G0"] and dropped["KXEPLGAME: the market was not open 7 days before the start"] == 1  # G1 opened a day before its start
    assert len(candle_requests(fake)) == after_one_hour + 2  # only G0's two markets were asked for at 7 days: a new window, not the one-hour candles
    collect(fake.client, cache, ["KXEPLGAME"], pause=0, lead_hours=168)
    collect(fake.client, cache, ["KXEPLGAME"], pause=0)
    assert len(candle_requests(fake)) == after_one_hour + 2  # both horizons come from the cache the second time


def test_the_other_horizons_are_reported_in_sections_and_only_the_pooled_group_and_the_sectors_are_tested(tmp_path):
    report = run(FakeKalshi().client, tmp_path, ["KXEPLGAME"], log_line=lambda s: None, horizons=(24, 168))
    assert "raw results, 24 hours before the start" in report and "raw results, 7 days before the start" in report
    assert "Median spread at this horizon" in report and "(descriptive only)" in report and "Brier score of the price is" in report
    assert "| Premier League | 1 | F |" in report and "descriptive |" in report  # the series row is shown but not tested
    default = run(FakeKalshi().client, tmp_path, ["KXEPLGAME"], log_line=lambda s: None)
    assert "raw results, 1 hour before the start" in default and "descriptive" not in default  # the first test is unchanged: every group tested


def test_a_group_outside_the_tested_set_gets_no_verdict():
    games = [game(f"E{i}", "0.50", "0.52", "0.47", "0.49", i % 2 == 0, day=i + 1) for i in range(10)]
    result = analyse(games, {"KXEPLGAME": FEE}, tested={"All"})
    assert result["All"]["strategies"]["F"]["verdict"] != "descriptive" and result["Premier League"]["strategies"]["F"]["verdict"] == "descriptive"


def test_the_gain_in_accuracy_as_the_game_nears_is_measured_on_the_same_games():
    far = [game("A", "0.45", "0.55", "0.40", "0.50", True), game("B", "0.40", "0.50", "0.45", "0.55", False)]
    near = [game("A", "0.80", "0.82", "0.17", "0.19", True), game("C", "0.60", "0.62", "0.35", "0.37", True)]
    arrival = information_arrival(far, near)
    assert arrival["games"] == 1 and arrival["horizon"] > arrival["one_hour"]  # on game A alone the nearer price is the better one


def test_the_horizons_option_is_checked(monkeypatch, capsys):
    for k, v in {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}.items():
        monkeypatch.setenv(k, v)
    for bad in ("x", "0", "24,-3", ""):
        assert cli.main(["price-test", "--horizons", bad]) == 2
    assert "--horizons must be hours" in capsys.readouterr().err
