import threading
import time
from datetime import UTC, datetime

import pytest

from app.config import SeriesEntry, load_settings
from app.games import GamesService, build_game
from tests.conftest import EMAIL, PASSWORD, needs_db

ENV = {
    "DATABASE_URL": "postgresql://u:p@db:5432/x",
    "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
    "SESSION_SECRET": "s" * 40,
}
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def market(event, suffix, label, bid, ask, occurrence="2026-10-12T22:00:00Z", close="2026-10-14T19:00:00Z", last="0.0000"):
    return {
        "ticker": f"{event}-{suffix}", "title": f"{label} wins", "yes_sub_title": label, "status": "active",
        "yes_bid_dollars": bid, "yes_ask_dollars": ask, "last_price_dollars": last, "volume_fp": "36114.22",
        "occurrence_datetime": occurrence, "close_time": close,
    }


def event(ticker, title, outcomes, **kw):
    return {"event_ticker": ticker, "series_ticker": ticker.split("-")[0], "title": title, "sub_title": "x (Oct 12)",
            "category": "Sports", "markets": [market(ticker, f"O{i}", *o, **kw) for i, o in enumerate(outcomes)]}


class FakeKalshi:
    def __init__(self, by_series, fail=(), delay=0.0, pages=None):
        self.by_series, self.fail, self.delay, self.pages = by_series, set(fail), delay, pages or {}
        self.calls = []
        self.running = self.max_running = 0
        self._lock = threading.Lock()

    def list_events(self, *, series_ticker, status=None, limit=None, with_nested_markets=None, cursor=None):
        with self._lock:
            self.calls.append((series_ticker, cursor, status, limit, with_nested_markets))
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            time.sleep(self.delay)
            if series_ticker in self.fail:
                raise RuntimeError("Kalshi request failed: boom")
            if series_ticker in self.pages:
                pages = self.pages[series_ticker]
                index = 0 if cursor is None else int(cursor)
                return {"events": pages[index], "cursor": str(index + 1) if index + 1 < len(pages) else ""}
            return {"events": self.by_series.get(series_ticker, []), "cursor": ""}
        finally:
            with self._lock:
                self.running -= 1


def service(kalshi, series="Soccer:KXEPL:Premier League,Tennis:KXATP:ATP,Baseball:KXMLB:MLB", clock=None, **env):
    settings = load_settings({**ENV, "SPORTS_SERIES": series, **env})
    clock = clock or (lambda: 0.0)
    return GamesService(lambda: kalshi, settings, clock=clock, now=lambda: NOW)


EPL = [event("KXEPL-26OCT12COVNEW", "Coventry vs Newcastle", [("Coventry", "0.2900", "0.3000"), ("Newcastle", "0.4300", "0.4400"), ("Tie", "0.2600", "0.2700")])]
ATP = [event("KXATP-26OCT13HURDAV", "Hurkacz vs Davidovich", [("Hurkacz", "0.5100", "0.5200"), ("Davidovich", "0.4700", "0.4900")], occurrence="2026-10-13T08:00:00Z")]
MLB = [event("KXMLB-26OCT161800TBCLE", "Game 1: Tampa Bay vs Cleveland", [("Tampa Bay", "0.5300", "0.5500"), ("Cleveland", "0.4400", "0.5000")], occurrence="2026-10-16T22:00:00Z")]


def test_a_game_is_one_entry_with_all_its_outcomes_prices_and_times():
    game = build_game(EPL[0], SeriesEntry("Soccer", "KXEPL", "Premier League"))
    assert game["title"] == "Coventry vs Newcastle" and game["sport"] == "Soccer" and game["league"] == "Premier League"
    assert game["starts_at"] == "2026-10-12T22:00:00+00:00"  # the game time, not the later close time
    assert game["closes_at"] == "2026-10-14T19:00:00+00:00"
    assert [(o["label"], o["bid"], o["ask"]) for o in game["outcomes"]] == [
        ("Coventry", "0.2900", "0.3000"), ("Newcastle", "0.4300", "0.4400"), ("Tie", "0.2600", "0.2700")]
    assert game["outcomes"][0]["market_ticker"] == "KXEPL-26OCT12COVNEW-O0"
    assert game["outcomes"][0]["last"] == "0.0000"  # kept as sent; the page does not use it


def test_events_without_markets_are_skipped_and_missing_times_are_none():
    entry = SeriesEntry("Soccer", "KXEPL", "PL")
    assert build_game({"event_ticker": "E", "markets": []}, entry) is None
    ev = {"event_ticker": "E", "title": "A vs B", "markets": [{"ticker": "E-1", "yes_sub_title": "A"}]}
    game = build_game(ev, entry)
    assert game["starts_at"] is None and game["closes_at"] is None and game["outcomes"][0]["bid"] is None


def test_games_from_all_series_are_combined_sorted_by_start_with_started_flag():
    s = service(FakeKalshi({"KXEPL": EPL, "KXATP": ATP, "KXMLB": MLB}))
    result = s.query()
    assert [g["title"] for g in result["games"]] == ["Coventry vs Newcastle", "Hurkacz vs Davidovich", "Game 1: Tampa Bay vs Cleveland"]
    assert [g["started"] for g in result["games"]] == [False, False, False] and result["hidden_started"] == 0
    assert result["sports"] == ["Soccer", "Tennis", "Baseball"] and result["total"] == 3 and result["errors"] == []


def test_started_games_are_hidden_by_default_and_counted_and_can_be_shown():
    early = event("KXEPL-A", "Started game", [("A", "0.5000", "0.5100")], occurrence="2026-10-12T10:00:00Z")
    nostart = {"event_ticker": "KXEPL-B", "title": "No time", "markets": [{"ticker": "KXEPL-B-1", "yes_sub_title": "X"}]}
    s = service(FakeKalshi({"KXEPL": [nostart] + EPL + [early]}))
    default = s.query()
    # Kalshi keeps finished or running games open until they settle; they would bury the upcoming ones.
    assert [g["title"] for g in default["games"]] == ["Coventry vs Newcastle", "No time"]
    assert default["hidden_started"] == 1 and default["total"] == 2
    shown = s.query(include_started=True)
    assert [(g["title"], g["started"]) for g in shown["games"]] == [("Started game", True), ("Coventry vs Newcastle", False), ("No time", False)]
    assert shown["hidden_started"] == 0


def test_filters_by_sport_and_text_and_limit():
    s = service(FakeKalshi({"KXEPL": EPL, "KXATP": ATP, "KXMLB": MLB}))
    assert [g["sport"] for g in s.query(sport="tennis")["games"]] == ["Tennis"]  # case does not matter
    assert [g["title"] for g in s.query(q="newcastle")["games"]] == ["Coventry vs Newcastle"]
    assert [g["title"] for g in s.query(q="premier league")["games"]] == ["Coventry vs Newcastle"]  # league is searched too
    limited = s.query(limit=2)
    assert len(limited["games"]) == 2 and limited["total"] == 3


def test_each_series_is_requested_for_open_events_with_markets():
    k = FakeKalshi({"KXEPL": EPL})
    service(k).get()
    assert sorted(c[0] for c in k.calls) == ["KXATP", "KXEPL", "KXMLB"]
    assert all(c[2:] == ("open", 200, True) for c in k.calls)


def test_a_failing_series_is_reported_and_the_others_still_show():
    s = service(FakeKalshi({"KXEPL": EPL, "KXMLB": MLB}, fail={"KXATP"}))
    result = s.query()
    assert [g["sport"] for g in result["games"]] == ["Soccer", "Baseball"]
    assert result["errors"] == [{"series": "KXATP", "league": "ATP", "error": "RuntimeError: Kalshi request failed: boom"}]


def test_results_are_cached_then_refetched_after_expiry():
    now = [0.0]
    k = FakeKalshi({"KXEPL": EPL})
    s = service(k, clock=lambda: now[0], GAMES_CACHE_SECONDS="60")
    s.get(); s.get()
    assert len(k.calls) == 3  # three series fetched once, the second call came from memory
    now[0] = 59.0; s.get()
    assert len(k.calls) == 3
    now[0] = 61.0; s.get()
    assert len(k.calls) == 6


def test_a_result_with_a_failed_series_is_kept_only_briefly_so_it_retries_soon():
    now = [0.0]
    k = FakeKalshi({"KXEPL": EPL}, fail={"KXATP"})
    s = service(k, clock=lambda: now[0], GAMES_CACHE_SECONDS="60")
    s.get()
    now[0] = 9.0; s.get()
    assert len(k.calls) == 3
    now[0] = 11.0; s.get()
    assert len(k.calls) == 6  # refetched after 10 s, not 60


def test_series_are_fetched_in_parallel_but_never_more_than_the_limit():
    series = ",".join(f"Soccer:KXS{i}" for i in range(12))
    k = FakeKalshi({}, delay=0.1)
    start = time.time()
    service(k, series=series, SPORTS_FETCH_CONCURRENCY="4").get()
    assert 1 < k.max_running <= 4
    assert time.time() - start < 0.1 * 12 * 0.8  # clearly faster than one after another


def test_simultaneous_page_loads_share_one_refresh():
    k = FakeKalshi({"KXEPL": EPL}, delay=0.2)
    s = service(k)
    threads = [threading.Thread(target=s.get) for _ in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert len(k.calls) == 3  # one fetch of the three series, not eight


def test_several_pages_of_events_are_followed():
    p1 = [event("KXEPL-1", "G1", [("A", "0.5000", "0.5100")])]
    p2 = [event("KXEPL-2", "G2", [("B", "0.5000", "0.5100")])]
    k = FakeKalshi({}, pages={"KXEPL": [p1, p2]})
    result = service(k, series="Soccer:KXEPL").query()
    assert sorted(g["title"] for g in result["games"]) == ["G1", "G2"]
    assert [c[1] for c in k.calls] == [None, "1"]


# --- settings ---------------------------------------------------------------

def test_default_series_list_covers_the_three_sports_and_is_announced(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.config")
    settings = load_settings(ENV)
    sports = {e.sport for e in settings.sports_series}
    assert sports == {"Soccer", "Baseball", "Tennis"} and len(settings.sports_series) == 15
    assert {"KXEPLGAME", "KXMLBGAME", "KXATPMATCH"} <= {e.ticker for e in settings.sports_series}
    assert "default list" in caplog.text  # the default is visible, not silent
    assert (settings.games_cache_seconds, settings.sports_fetch_concurrency) == (60, 6)


def test_custom_series_list_with_and_without_labels():
    s = load_settings({**ENV, "SPORTS_SERIES": "Soccer:KXEPLGAME:Premier League, Tennis:KXATPMATCH"})
    assert [(e.sport, e.ticker, e.league) for e in s.sports_series] == [("Soccer", "KXEPLGAME", "Premier League"), ("Tennis", "KXATPMATCH", "KXATPMATCH")]


@pytest.mark.parametrize("bad", ["KXEPLGAME", "Soccer:", ":KXEPLGAME", "Soccer:kx epl", "Soccer:KXA,Soccer:KXA", " , "])
def test_bad_series_settings_stop_startup(bad):
    from app.config import SettingsError

    with pytest.raises(SettingsError, match="SPORTS_SERIES"):
        load_settings({**ENV, "SPORTS_SERIES": bad})


def test_an_empty_series_setting_means_the_default_list():
    assert len(load_settings({**ENV, "SPORTS_SERIES": ""}).sports_series) == 15


# --- endpoint ---------------------------------------------------------------

@needs_db
def test_endpoint_needs_login_and_serves_filtered_games(make_client):
    H = {"X-Requested-With": "t"}
    with make_client() as client:
        assert client.get("/api/games").status_code == 401
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        client.app.state.games = service(FakeKalshi({"KXEPL": EPL, "KXATP": ATP, "KXMLB": MLB}))
        body = client.get("/api/games").json()
        assert [g["title"] for g in body["games"]][0] == "Coventry vs Newcastle" and body["sports"] == ["Soccer", "Tennis", "Baseball"]
        assert [g["sport"] for g in client.get("/api/games?sport=Tennis").json()["games"]] == ["Tennis"]
        assert client.get("/api/games?q=cleveland").json()["total"] == 1
        assert client.get("/api/games?include_started=true").status_code == 200
        assert client.get("/api/games?limit=0").status_code == 422
        assert client.get("/api/games?limit=501").status_code == 422
