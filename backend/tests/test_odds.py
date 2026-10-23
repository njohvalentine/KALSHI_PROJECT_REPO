"""The bookmaker benchmark: margin removal, matching a game, the key kept secret, credits, caching, and the record. Fakes only."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app import odds as odds_module
from app.config import SettingsError, load_settings
from app.odds import (
    OddsClient, OddsOutOfCredits, OddsUnauthorized, book_for_game, book_prices, find_game, hide_key_in_logs, same_team, sport_keys_for,
)
from app.research.records import build_records
from app.research.schemas import GameInfo

BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
KEY = "0123456789abcdef0123456789abcdef"
START = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)


def book(key, home, draw, away):
    return {"key": key, "markets": [{"key": "h2h", "outcomes": [{"name": "Roma", "price": home}, {"name": "Draw", "price": draw}, {"name": "Real Madrid", "price": away}]}]}


def event(home="AS Roma", away="Real Madrid", at=START, books=None):
    books = books if books is not None else [book("a", 4.0, 3.6, 1.9), book("b", 4.2, 3.7, 1.85), book("c", 4.1, 3.5, 1.9), book("pinnacle", 4.3, 3.7, 1.9),
                                             book("betfair_ex_eu", 2.0, 2.0, 2.0)]
    for b in books:  # the feed's team names
        for o in b["markets"][0]["outcomes"]:
            o["name"] = {"Roma": home, "Real Madrid": away}.get(o["name"], o["name"])
    return {"home_team": home, "away_team": away, "commence_time": at.isoformat().replace("+00:00", "Z"), "bookmakers": books}


def test_margin_is_removed_the_consensus_is_the_median_and_exchanges_are_left_out():
    prices = book_prices(event(), 3)
    def home(h, d, a):  # the home team's price with the margin removed by scaling to 1
        return (1 / h) / (1 / h + 1 / d + 1 / a)

    each = sorted([home(4.0, 3.6, 1.9), home(4.2, 3.7, 1.85), home(4.1, 3.5, 1.9), home(4.3, 3.7, 1.9)])
    assert prices["AS Roma"]["count"] == 4  # a, b, c and pinnacle; the exchange (which would give 1/3) is not in the consensus
    assert prices["AS Roma"]["probability"] == pytest.approx((each[1] + each[2]) / 2)
    assert prices["AS Roma"]["pinnacle"] == pytest.approx(home(4.3, 3.7, 1.9))


def test_a_bookmaker_with_the_wrong_number_of_outcomes_or_a_bad_price_is_skipped():
    bad = [book("a", 4.0, 3.6, 1.9), {"key": "b", "markets": [{"key": "h2h", "outcomes": [{"name": "Roma", "price": 1.5}, {"name": "Real Madrid", "price": 2.5}]}]},
           book("c", 1.0, 3.5, 1.9)]
    prices = book_prices(event(books=bad), 3)
    assert prices["AS Roma"]["count"] == 1


@pytest.mark.parametrize("a,b,expected", [
    ("Roma", "AS Roma", True), ("Bodoe/Glimt", "Bodø/Glimt", True), ("PSG", "Paris Saint-Germain", True), ("Dortmund", "Borussia Dortmund", True),
    ("Los Angeles D", "Los Angeles Dodgers", True), ("DC United", "D.C. United", True), ("Manchester City", "Manchester United", False),
    ("Slovan Bratislava", "ŠK Slovan Bratislava", True), ("New York RB", "New York Red Bulls", True), ("Roma", "Real Madrid", False),
])
def test_team_names_match_across_spellings_and_not_across_teams(a, b, expected):
    assert same_team(a, b) is expected


def test_a_game_must_match_by_both_teams_and_start_time_exactly_once():
    ok = event()
    assert find_game([ok], "Roma vs Real Madrid", START)[0] is ok
    assert find_game([ok], "Real Madrid vs Roma", START)[0] is ok  # either order
    assert find_game([event(at=START + timedelta(hours=5))], "Roma vs Real Madrid", START)[0] is None  # a different day or slot
    assert "several" in find_game([ok, event()], "Roma vs Real Madrid", START)[1]
    assert find_game([ok], "Game 3: Roma vs Real Madrid", START)[0] is ok
    assert find_game([ok], "Roma", START)[0] is None and find_game([ok], "Roma vs Real Madrid", None)[0] is None


def test_the_sport_key_comes_from_the_series_and_tennis_from_the_active_tournaments():
    active = {"soccer_epl", "tennis_atp_shanghai_masters", "tennis_wta_wuhan_open"}
    assert sport_keys_for("KXEPLGAME", active) == ["soccer_epl"] and sport_keys_for("KXMLBGAME", active) == []  # not active: no credits spent
    assert sport_keys_for("KXATPMATCH", active) == ["tennis_atp_shanghai_masters"] and sport_keys_for("KXWTAMATCH", active) == ["tennis_wta_wuhan_open"]
    assert sport_keys_for("KXATPCHALLENGERMATCH", active) == []


class FakeHttp:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        status, body, headers = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return httpx2.Response(status, json=body, headers=headers, request=httpx2.Request("GET", url))


def client_with(responses, **kw):
    http = FakeHttp(responses)
    return OddsClient(KEY, "eu", 10, client=http, **kw), http


SPORTS = [{"key": "soccer_uefa_champs_league", "active": True}]


def game_args(**over):
    args = dict(event_ticker="KXUCLGAME-26OCT14ROMRMA", title="Roma vs Real Madrid", starts_at=START, outcome_names=["Roma", "Real Madrid", "Tie"],
                outcome_tickers=["T-ROM", "T-RMA", "T-TIE"])
    return {**args, **over}


def test_the_prices_of_a_game_are_found_and_one_read_serves_two_games_of_a_league():
    c, http = client_with([(200, SPORTS, {}), (200, [event()], {"x-requests-remaining": "480"})])
    got = asyncio.run(book_for_game(c, **game_args()))
    assert got["note"] is None and set(got["by_ticker"]) == {"T-ROM", "T-RMA", "T-TIE"}
    assert abs(sum(v["probability"] for v in got["by_ticker"].values()) - 1) < 0.02
    asyncio.run(book_for_game(c, **game_args()))
    assert [u.rsplit("/", 1)[-1] for u, _ in http.calls] == ["sports", "odds"] and c.credits_remaining == 480
    assert http.calls[1][1]["regions"] == "eu" and http.calls[1][1]["markets"] == "h2h"


def test_no_match_a_league_without_a_source_or_a_failure_leaves_a_note_and_never_raises():
    c, _ = client_with([(200, SPORTS, {}), (200, [event()], {})])
    assert "no game of the odds feed matched" in asyncio.run(book_for_game(c, **game_args(title="Roma vs Lazio")))["note"]
    assert "no bookmaker source" in asyncio.run(book_for_game(c, **game_args(event_ticker="KXATPCHALLENGERMATCH-26OCT14X")))["note"]
    assert "off" in asyncio.run(book_for_game(None, **game_args()))["note"]
    broken, _ = client_with([(500, {}, {})])
    note = asyncio.run(book_for_game(broken, **game_args()))["note"]
    assert "could not be read" in note and "OddsError" in note


def test_a_wrong_key_and_used_up_credits_are_named_and_the_key_never_appears_in_the_error():
    wrong, _ = client_with([(401, {"error_code": "INVALID_KEY"}, {})])
    with pytest.raises(OddsUnauthorized) as caught:
        asyncio.run(wrong.active_sport_keys())
    assert KEY not in str(caught.value)
    out, http = client_with([(401, {"error_code": "OUT_OF_USAGE_CREDITS"}, {"x-requests-remaining": "0"})])
    with pytest.raises(OddsOutOfCredits):
        asyncio.run(out.active_sport_keys())
    with pytest.raises(OddsOutOfCredits):  # not called again for a while
        asyncio.run(out.odds("soccer_epl"))
    assert len(http.calls) == 1


def test_low_credits_are_warned_about(caplog):
    c, _ = client_with([(200, SPORTS, {"x-requests-remaining": "12"})])
    with caplog.at_level(logging.WARNING, logger="app.odds"):
        asyncio.run(c.active_sport_keys())
    assert "only 12 credits left" in caplog.text


def test_the_key_is_hidden_in_the_log_lines_the_real_http_library_writes(caplog):
    """The library logs the URL as an object (not a string), so this runs a real request through a mock transport."""
    hide_key_in_logs()
    hide_key_in_logs()  # twice is fine

    async def go():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json=[]))) as c:
            await c.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": KEY, "all": "true"})

    with caplog.at_level(logging.INFO, logger="httpx2"):
        asyncio.run(go())
    assert "HTTP Request" in caplog.text and KEY not in caplog.text and "apiKey=<hidden>" in caplog.text


def test_a_malformed_log_call_does_not_make_the_key_filter_raise_and_is_still_masked():
    from app.odds import _HideKey

    record = logging.LogRecord("httpx2", logging.INFO, "f.py", 1, f"GET https://api.the-odds-api.com/v4/sports?apiKey={KEY} %s %s", ("only one",), None)
    assert _HideKey().filter(record) is True and KEY not in record.getMessage() and "apiKey=<hidden>" in record.getMessage()


def test_the_record_keeps_the_bookmaker_price_or_the_reason_and_only_winner_markets_get_one():
    game = GameInfo(event_ticker="KXUCLGAME-26OCT14ROMRMA", title="Roma vs Real Madrid", starts_at=START.isoformat(), outcome_names=["Roma", "Real Madrid", "Tie"],
                    outcome_tickers=["T-ROM", "T-RMA", "T-TIE"])
    outcome = lambda t, kind="winner": {"market_ticker": t, "kind": kind, "outcome": t, "probability": 0.4, "min": 0.3, "max": 0.5}  # noqa: E731
    prediction = {"outcomes": [outcome("T-ROM"), outcome("T-OVER", "total")], "forecasters_valid": 3, "evidence": "supported", "supported_claims": 6}
    book_info = {"at": START, "by_ticker": {"T-ROM": {"probability": 0.2312345, "pinnacle": 0.22, "count": 40}}, "note": None}
    rom, over = build_records("r1", game, prediction, {"outcomes": []}, None, START - timedelta(hours=2), book_info)
    assert rom.book_probability == Decimal("0.2312") and rom.book_pinnacle == Decimal("0.2200") and rom.book_count == 40 and rom.book_note is None
    assert over.book_probability is None and "only read for winner markets" in over.book_note
    none, _ = build_records("r1", game, prediction, {"outcomes": []}, None, START, {"at": None, "by_ticker": {}, "note": "no game matched"})
    assert none.book_probability is None and none.book_note == "no game matched"
    assert build_records("r1", game, prediction, {"outcomes": []}, None, START)[0].book_note == "no bookmaker price was looked for"


def test_settings_refuse_the_benchmark_on_without_a_good_key_and_keep_it_off_by_default():
    assert load_settings(BASE).odds_enabled is False
    with pytest.raises(SettingsError, match="ODDS_ENABLED=true needs ODDS_API_KEY"):
        load_settings({**BASE, "ODDS_ENABLED": "true"})
    with pytest.raises(SettingsError, match="does not look like"):
        load_settings({**BASE, "ODDS_ENABLED": "true", "ODDS_API_KEY": "short"})
    with pytest.raises(SettingsError, match="ODDS_REGIONS"):
        load_settings({**BASE, "ODDS_ENABLED": "true", "ODDS_API_KEY": KEY, "ODDS_REGIONS": "mars"})
    ok = load_settings({**BASE, "ODDS_ENABLED": "true", "ODDS_API_KEY": KEY, "ODDS_REGIONS": "eu,uk"})
    assert ok.odds_enabled and ok.odds_regions == "eu,uk" and ok.odds_cache_minutes == 10


def test_nothing_in_the_odds_module_can_send_or_trade():
    source = open(odds_module.__file__).read()
    assert ".post(" not in source and "orders" not in source.lower()
