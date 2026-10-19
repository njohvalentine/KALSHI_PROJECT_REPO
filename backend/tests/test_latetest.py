"""The late-game test: the entry candle, the NO bet and its cost, the band and filters, fixed-close series, the rule's verdicts and the CLI. No network."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app import cli
from app.kalshi import KalshiClient
from app.research.compare import FeeInfo
from app.research.latetest import ENTRY, LateGame, analyse, collect, fixed_close, format_report, late_bets, late_verdict
from app.research.pricetest import Cache

FEE = FeeInfo("quadratic", Decimal(1), "series")
D = Decimal
CLOSE = 1_000_000


def candle(end, bid, ask, volume="20"):
    return {"end_period_ts": end, "yes_bid": {"close": bid}, "yes_ask": {"close": ask}, "volume": volume}


def book(bid="0.28", ask="0.30", n=6, end=CLOSE - ENTRY):
    return [candle(end - 60 * i, bid, ask, "5") for i in range(n)]


def test_the_entry_candle_is_the_last_one_ending_at_least_five_minutes_before_the_close():
    candles = book("0.28", "0.30") + [candle(CLOSE - 100, "0.50", "0.52"), candle(CLOSE - ENTRY + 30, "0.50", "0.52")]  # too close to the close
    [(result, _)] = late_bets(candles, CLOSE, won=False, fee=FEE)
    no_ask = 1 - D("0.28")
    assert result == 1 - no_ask - D("0.07") * no_ask * (1 - no_ask)  # NO at one minus the YES bid, plus the fee; the NO wins


def test_a_yes_win_loses_the_no_stake():
    [(result, _)] = late_bets(book(), CLOSE, won=True, fee=FEE)
    assert result < -D("0.72")


@pytest.mark.parametrize("bid,ask,bets", [("0.09", "0.11", 1), ("0.08", "0.10", 0), ("0.39", "0.41", 1), ("0.40", "0.42", 0)])
def test_the_band_is_ten_to_forty_cents_on_the_middle_price(bid, ask, bets):
    assert len(late_bets(book(bid, ask), CLOSE, False, FEE)) == bets


def test_filters_count_their_reasons():
    drop = Counter()
    assert late_bets(book("0.20", "0.32"), CLOSE, False, FEE, dropped=drop) == [] and drop["spread wider than 10 cents"] == 1
    quiet = [candle(CLOSE - ENTRY - 60 * i, "0.28", "0.30", "1") for i in range(6)]  # 5 contracts in the window before the entry candle
    assert late_bets(quiet, CLOSE, False, FEE, dropped=drop) == [] and drop["fewer than 10 contracts traded in the 5 minutes before"] == 1
    assert late_bets([candle(CLOSE - 60, "0.28", "0.30")], CLOSE, False, FEE, dropped=drop) == [] and drop["no bid and ask before the entry"] == 1


def test_a_quote_that_did_not_change_is_marked_stale():
    [(_, stale)] = late_bets(book(), CLOSE, False, FEE)
    assert stale
    moving = book()
    moving[2] = candle(CLOSE - ENTRY - 120, "0.30", "0.32", "5")
    [(_, stale)] = late_bets(moving, CLOSE, False, FEE)
    assert not stale


def test_series_with_a_fixed_close_are_recognised():
    soccer = [(i * 10_000, i * 10_000 + 120 * 60) for i in range(20)]
    nba = [(i * 10_000, i * 10_000 + (130 + 5 * (i % 9)) * 60) for i in range(20)]
    assert fixed_close(soccer) and not fixed_close(nba)


def games(n, mean_result):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [LateGame(f"E{i}", "KXNBAGAME", start + timedelta(days=i), {e: [(D(str(mean_result)) + (D("0.01") if i % 2 else D("-0.01")), False)] * 2 for e in (300, 600, 120)}) for i in range(n)]


def test_the_rule_found_not_confirmed_no_pattern_and_too_few_bets():
    r = analyse(games(200, 0.20))["All"]["rows"][ENTRY]
    assert r["verdict"] == "FOUND" and r["first"]["bets"] == 200
    assert analyse(games(200, -0.20))["All"]["rows"][ENTRY]["verdict"] == "no pattern"
    assert analyse(games(30, 0.20))["All"]["rows"][ENTRY]["verdict"] == "too few bets"
    assert analyse(games(200, 0.20))["All"]["rows"][600]["verdict"] == "descriptive"
    first = {"bets": 500, "mean": 0.1, "ci99": (0.0, 0.2)}
    assert late_verdict(first, {"bets": 500, "mean": 0.1, "ci99": (-0.01, 0.2)}) == "not confirmed"


def test_the_report_says_it_is_not_tradable_and_names_excluded_series():
    text = format_report(analyse(games(200, 0.0)), Counter({"spread wider than 10 cents": 3}), 200, ["KXEPLGAME"])
    assert "NOT a tradable strategy" in text and "KXEPLGAME" in text and "spread wider than 10 cents: 3" in text


class Fake:
    """A Kalshi client with a few games: one series with a fixed close, one with a real one. Counts the candle requests."""

    def __init__(self):
        self.candle_calls = 0

    def get_series(self, series):
        return {"series": {"fee_type": "quadratic", "fee_multiplier": 1}}

    def list_historical_markets(self, **kw):
        out = []
        for series, extra in (("KXEPLGAME", lambda i: 120), ("KXNBAGAME", lambda i: 120 + 10 * i)):
            for i in range(12):
                close = datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=i, minutes=extra(i))
                for side, res in (("A", "yes"), ("B", "no")):
                    out.append({"ticker": f"{series}-{i}-{side}", "event_ticker": f"{series}-{i}", "result": res, "close_time": close.isoformat(), "open_time": None})
        return {"markets": [m for m in out if m["ticker"].startswith(kw["series_ticker"])], "cursor": None}

    def list_milestones(self, **kw):
        ev = kw["related_event_ticker"]
        i = int(ev.rsplit("-", 1)[1])
        return {"milestones": [{"primary_event_tickers": [ev], "start_date": (datetime(2026, 1, 1, 10, tzinfo=UTC) + timedelta(days=i)).isoformat()}]}

    def get_historical_candlesticks(self, ticker, **kw):
        self.candle_calls += 1
        end = kw["end_ts"] - ENTRY
        bid, ask = ("0.28", "0.30") if ticker.endswith("A") else ("0.70", "0.72")
        return {"candlesticks": [candle(end - 60 * i, bid, ask, "5") for i in range(6)]}


def test_collect_leaves_out_the_fixed_close_series_and_a_second_run_downloads_nothing(tmp_path):
    fake, cache = Fake(), Cache(tmp_path)
    got, dropped, excluded = collect(fake, cache, ["KXEPLGAME", "KXNBAGAME"], workers=1, pause=0)
    assert excluded == ["KXEPLGAME"] and len(got) == 12
    assert all(len(g.bets[ENTRY]) == 1 for g in got)  # only the 28 cent outcome is in the band
    calls = fake.candle_calls
    assert calls == 24
    collect(fake, cache, ["KXNBAGAME"], workers=1, pause=0)
    assert fake.candle_calls == calls


def test_the_cli_reads_its_options_and_writes_the_report(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    monkeypatch.setattr("app.research.latetest.run", lambda client, cache_dir, **kw: seen.update(cache=cache_dir, workers=kw["workers"]) or "REPORT\n")
    monkeypatch.setattr(cli, "load_settings", lambda env: type("S", (), {"kalshi_api_base": "http://x"})(), raising=False)
    monkeypatch.setattr("app.config.load_settings", lambda env: type("S", (), {"kalshi_api_base": "http://x"})())
    out = tmp_path / "r.md"
    assert cli.main(["late-test", "--cache-dir", str(tmp_path / "c"), "--workers", "2", "--out", str(out)]) == 0
    assert out.read_text() == "REPORT\n" and seen["workers"] == 2
