"""The free check before research: the rule, the credit floor, the league limit, and what is saved."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.config import load_settings
from app.odds import OddsError
from app.screening import screen_games
from tests.conftest import EMAIL, PASSWORD, needs_db

ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
NOW = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
START = NOW + timedelta(hours=5)
H = {"X-Requested-With": "t"}


class FakeOdds:
    def __init__(self, active=("soccer_epl",), events=None, credits=400, fail=()):
        self.active, self.events, self.credits_remaining, self.fail, self.calls = set(active), events or {}, credits, set(fail), []

    async def active_sport_keys(self):
        return self.active

    async def odds(self, key):
        self.calls.append(key)
        if key in self.fail:
            raise OddsError("down")
        return self.events.get(key, [])


class FakeKalshi:
    def close(self):
        pass

    def get_series(self, series):
        return {"series": {"fee_type": "quadratic", "fee_multiplier": 1}}


def feed_event(home="Arsenal", away="Chelsea", at=START):
    prices = {home: 2.0, "Draw": 4.0, away: 4.0}  # 50% / 25% / 25%, no margin
    books = [{"key": k, "markets": [{"key": "h2h", "outcomes": [{"name": n, "price": p} for n, p in prices.items()]}]} for k in ("a", "b", "c")]
    return {"home_team": home, "away_team": away, "commence_time": at.isoformat().replace("+00:00", "Z"), "bookmakers": books}


def game(ticker="KXEPLGAME-26OCT17ARSCHE", title="Arsenal vs Chelsea", ask="0.40", ask_size="100", start=START, outcomes=None):
    t = ticker
    rows = outcomes or [("Arsenal", ask, "0.39", ask_size), ("Tie", "0.27", "0.26", "100"), ("Chelsea", "0.28", "0.27", "100")]
    return {"event_ticker": t, "title": title, "sport": "Soccer", "league": "Premier League", "starts_at": start.isoformat(),
            "outcomes": [{"market_ticker": f"{t}-{i}", "label": n, "bid": b, "ask": a, "ask_size": s, "bid_size": "100"} for i, (n, a, b, s) in enumerate(rows)]}


def screen(games, odds, **env):
    return asyncio.run(screen_games(games, odds, FakeKalshi(), load_settings(ENV | env), {}, NOW))


def test_a_gap_of_at_least_five_cents_after_fees_with_enough_contracts_is_worth_researching():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]})
    out = screen([game()], odds)
    r = out["results"]["KXEPLGAME-26OCT17ARSCHE"]
    assert r["status"] == "promising" and "Worth researching" in r["text"] and "Arsenal at 50%" in r["text"] and "“yes” at 40¢" in r["text"]
    assert r["best"]["edge"] > 0.05 and r["best"]["book_count"] == 3
    assert len(out["rows"]) == 3 and sum(1 for row in out["rows"] if row.passes) == 1  # one row per outcome, saved


def test_no_gap_or_too_few_contracts_is_not_promising():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]})
    a = screen([game(ask="0.50")], odds)["results"]["KXEPLGAME-26OCT17ARSCHE"]
    assert a["status"] == "not_promising" and "too few contracts" not in a["text"]
    b = screen([game(ask_size="5")], odds)["results"]["KXEPLGAME-26OCT17ARSCHE"]
    assert b["status"] == "not_promising" and "too few contracts offered" in b["text"]


def test_a_league_without_a_source_or_a_game_the_feed_does_not_list_cannot_be_screened():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]})
    out = screen([game("KXFOOGAME-26OCT17ARSCHE"), game("KXEPLGAME-26OCT17XYZABC", title="Roma vs Lazio")], odds)["results"]
    assert out["KXFOOGAME-26OCT17ARSCHE"]["status"] == "cannot" and "no bookmaker source" in out["KXFOOGAME-26OCT17ARSCHE"]["text"]
    assert out["KXEPLGAME-26OCT17XYZABC"]["status"] == "cannot" and "no game of the odds feed matched" in out["KXEPLGAME-26OCT17XYZABC"]["text"]


def test_started_games_and_games_beyond_the_hours_ahead_are_not_checked():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]})
    out = screen([game(start=NOW - timedelta(hours=1)), game("KXEPLGAME-26OCT19LATE", start=NOW + timedelta(hours=40))], odds)
    assert out["results"] == {} and odds.calls == []  # nothing to check, nothing read
    far = screen([game("KXEPLGAME-26OCT19LATE", start=NOW + timedelta(hours=40))], odds, SCREEN_HOURS_AHEAD="48")["results"]
    assert "KXEPLGAME-26OCT19LATE" in far


def test_one_read_serves_all_the_games_of_a_league():
    odds = FakeOdds(events={"soccer_epl": [feed_event(), feed_event("Everton", "Fulham")]})
    screen([game(), game("KXEPLGAME-26OCT17EVEFUL", title="Everton vs Fulham")], odds)
    assert odds.calls == ["soccer_epl"]


def test_below_the_credit_floor_nothing_is_read():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]}, credits=50)
    out = screen([game()], odds)
    assert odds.calls == [] and out["results"] == {} and "Only 50 odds credits" in out["notes"][0] and out["credits"]["remaining"] == 50
    assert screen([game()], FakeOdds(events={"soccer_epl": [feed_event()]}, credits=50), SCREEN_MIN_CREDITS_LEFT="0")["results"]  # no floor: it reads


def test_only_the_busiest_leagues_are_read_and_the_rest_are_listed_as_not_checked():
    odds = FakeOdds(active=("soccer_epl", "soccer_spain_la_liga"), events={"soccer_epl": [feed_event(), feed_event("Everton", "Fulham")], "soccer_spain_la_liga": [feed_event("Roma", "Lazio")]})
    games = [game(), game("KXEPLGAME-26OCT17EVEFUL", title="Everton vs Fulham"), game("KXLALIGAGAME-26OCT17ROMLAZ", title="Roma vs Lazio")]
    out = screen(games, odds, SCREEN_MAX_LEAGUES="1")
    assert odds.calls == ["soccer_epl"] and out["results"]["KXLALIGAGAME-26OCT17ROMLAZ"]["status"] == "not_checked" and "SCREEN_MAX_LEAGUES" in out["notes"][0]


def test_a_tennis_game_is_looked_for_under_every_tournament_and_found_under_the_right_one():
    odds = FakeOdds(active=("tennis_atp_a", "tennis_atp_b"), events={"tennis_atp_b": [feed_event("Alcaraz", "Sinner")]})
    two_way = [("Alcaraz", "0.40", "0.39", "100"), ("Sinner", "0.62", "0.60", "100")]
    # the feed prices a 2-way game: 50 / 50
    odds.events["tennis_atp_b"][0]["bookmakers"] = [{"key": k, "markets": [{"key": "h2h", "outcomes": [{"name": "Alcaraz", "price": 2.0}, {"name": "Sinner", "price": 2.0}]}]} for k in ("a", "b", "c")]
    out = screen([game("KXATPMATCH-26OCT17ALCSIN", title="Alcaraz vs Sinner", outcomes=two_way)], odds)["results"]["KXATPMATCH-26OCT17ALCSIN"]
    assert sorted(odds.calls) == ["tennis_atp_a", "tennis_atp_b"] and out["status"] == "promising"


def test_a_failed_read_makes_its_games_cannot_be_screened_and_never_raises():
    odds = FakeOdds(events={"soccer_epl": [feed_event()]}, fail=("soccer_epl",))
    r = screen([game()], odds)["results"]["KXEPLGAME-26OCT17ARSCHE"]
    assert r["status"] == "cannot" and "could not be read" in r["text"]


def test_the_feed_off_says_so():
    out = screen([game()], None)
    assert out["results"] == {} and "bookmaker feed is off" in out["notes"][0]


@needs_db
def test_the_endpoint_saves_one_row_per_outcome_and_the_list_alone_reads_nothing(make_client):
    client = make_client()
    odds = FakeOdds(events={"soccer_epl": [feed_event()]})
    with client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=H)
        client.app.state.odds, client.app.state.kalshi = odds, FakeKalshi()
        client.app.state.games.query = lambda sport, q, limit, include_started, more: {"games": [game(start=datetime.now(UTC) + timedelta(hours=5))]}
        assert odds.calls == []
        assert client.post("/api/games/screen").status_code == 403  # no X-Requested-With header: nothing was read
        assert client.get("/api/games/screen").status_code == 405  # a GET no longer does the work
        assert odds.calls == []
        body = client.post("/api/games/screen", headers=H).json()
        assert odds.calls == ["soccer_epl"] and list(body["results"]) == ["KXEPLGAME-26OCT17ARSCHE"]
    with make_client.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM screenings")).scalar_one() == 3
    with make_client() as anonymous:
        assert anonymous.post("/api/games/screen", headers=H).status_code == 401
