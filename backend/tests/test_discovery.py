"""Discovery of all sports on Kalshi: the series catalog, games from milestones, the Games list, 'not yet measured', the NBA companions."""

from datetime import UTC, datetime

from app.config import load_settings
from app.discovery import SeriesCatalog, is_game_series, league_of, upcoming_series
from app.games import GamesService
from app.monitor import UNTESTED, alert_text
from app.opportunities import build_row
from app.research.markets import attach_companions
from app.research.prompts import PLANNER_INSTRUCTIONS
from app.research.records import build_records
from app.research.schemas import GameInfo
from tests.test_games import ENV, FakeKalshi, event
from tests.test_records import comparison, prediction

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
SERIES = [
    {"ticker": "KXNBAGAME", "title": "NBA Game", "tags": ["Basketball"]},
    {"ticker": "KXNBASPREAD", "title": "NBA Spread", "tags": ["Basketball"]},          # a companion, not a game
    {"ticker": "KXEBASKETGAME", "title": "eBasketball Game", "tags": ["Esports", "Basketball"]},  # an excluded tag
    {"ticker": "KXEPLGAME", "title": "Premier League Game", "tags": ["Soccer"]},       # a measured series
    {"ticker": "KXEREDGAME", "title": "Eredivisie Game", "tags": ["Soccer"]},          # another league of a measured sport
    {"ticker": "KXNBAMVP", "title": "NBA MVP", "tags": ["Basketball"]},                # a future
    {"ticker": "KXNOTAGGAME", "title": "Untagged Game", "tags": []},
]


def milestone(start, *tickers):
    return {"start_date": start, "primary_event_tickers": list(tickers), "related_event_tickers": list(tickers), "type": "whatever"}


MILESTONES = [[
    milestone("2026-10-13T00:30:00Z", "KXNBAGAME-26OCT13DENLAC", "KXNBASPREAD-26OCT13DENLAC"),
    milestone("2026-10-13T02:00:00Z", "KXNBAGAME-26OCT13BKNMIA"),
    milestone("2026-10-13T03:00:00Z", "KXEBASKETGAME-26OCT13AB"),
    milestone("2026-10-13T18:00:00Z", "KXEREDGAME-26OCT13AJXPSV", "KXEREDTOTAL-26OCT13AJXPSV"),
    milestone("2026-10-13T19:00:00Z", "KXEPLGAME-26OCT13COVNEW"),
    milestone("2026-10-01T19:00:00Z", "KXNBAGAME-26OCT01OLD"),  # long over: not coming up
    milestone("2026-10-13T20:00:00Z", "KXNOTAGGAME-26OCT13ZZ"),
]]
NBA = [event("KXNBAGAME-26OCT13DENLAC", "Denver vs Los Angeles C", [("Denver", "0.4000", "0.4200"), ("Los Angeles C", "0.5800", "0.6000")]),
       event("KXNBAGAME-26OCT13BKNMIA", "Brooklyn vs Miami", [("Brooklyn", "0.3000", "0.3200"), ("Miami", "0.6800", "0.7000")])]
EPL = [event("KXEPLGAME-26OCT13COVNEW", "Coventry vs Newcastle", [("Coventry", "0.2900", "0.3000"), ("Newcastle", "0.4300", "0.4400"), ("Tie", "0.2600", "0.2700")])]
ERED = [event("KXEREDGAME-26OCT13AJXPSV", "Ajax vs PSV", [("Ajax", "0.3000", "0.3200"), ("PSV", "0.5000", "0.5200"), ("Tie", "0.2000", "0.2300")])]


def service(measured=None, series="Soccer:KXEPLGAME:Premier League", **env):
    kalshi = FakeKalshi({"KXNBAGAME": NBA, "KXEPLGAME": EPL, "KXEREDGAME": ERED}, series=SERIES, milestone_pages=MILESTONES)
    settings = load_settings({**ENV, "SPORTS_SERIES": series, **env})
    return GamesService(lambda: kalshi, settings, clock=lambda: 0.0, now=lambda: NOW, measured=(lambda: measured or {})), kalshi


def test_only_series_of_single_games_with_a_sport_tag_and_no_excluded_tag_are_discovered():
    kalshi = FakeKalshi({}, series=SERIES)
    found = SeriesCatalog(lambda: kalshi, ("Esports", "Video games")).entries()
    assert set(found) == {"KXNBAGAME", "KXEPLGAME", "KXEREDGAME"}  # not the spread, the future, the esports game, the untagged one
    assert (found["KXNBAGAME"].sport, found["KXNBAGAME"].league) == ("Basketball", "NBA")
    assert is_game_series("ATP Challenger Match") and is_game_series("UFC Fight") and not is_game_series("NBA Total Points")
    assert league_of("Champions League Game") == "Champions League" and league_of("Odd title") == "Odd title"


def test_the_series_list_is_read_once_a_day_and_the_exclusions_can_be_changed():
    kalshi = FakeKalshi({}, series=SERIES)
    ticks = [0.0]
    catalog = SeriesCatalog(lambda: kalshi, ("Esports",), clock=lambda: ticks[0])
    catalog.entries()
    ticks[0] = 3600
    catalog.entries()
    assert kalshi.series_calls == 1
    ticks[0] = 25 * 3600
    catalog.entries()
    assert kalshi.series_calls == 2
    assert "KXEBASKETGAME" in SeriesCatalog(lambda: FakeKalshi({}, series=SERIES), ("Video games",)).entries()  # not excluded when not listed


def test_milestones_are_counted_per_series_from_the_main_event_tickers_of_games_coming_up():
    counts = upcoming_series(MILESTONES[0], "2026-10-12T06:00:00Z")
    assert counts["KXNBAGAME"] == 2 and counts["KXNBASPREAD"] == 1 and counts["KXEREDGAME"] == 1 and "KXNBAGAME-26OCT01OLD" not in counts
    assert upcoming_series([milestone("2026-10-13T00:00:00Z", "KXA-1", "KXA-2")], "2026-10-12T06:00:00Z") == {"KXA": 1}  # once per milestone


def test_the_list_offers_other_sports_and_extra_leagues_with_the_number_of_games_and_loads_nothing_for_them():
    s, kalshi = service()
    result = s.query()
    assert [g["title"] for g in result["games"]] == ["Coventry vs Newcastle"]  # only the measured series are loaded
    assert result["more_sports"] == [
        {"sport": "Basketball", "games": 2, "series": 1, "also_measured": False},
        {"sport": "Soccer", "games": 1, "series": 1, "also_measured": True},  # Eredivisie: another league of a measured sport
    ]
    assert all(call[0] == "KXEPLGAME" for call in kalshi.calls)


def test_picking_a_sport_with_more_loads_its_discovered_series_and_marks_games_of_unmeasured_sports():
    s, _ = service(measured={"Soccer": 25})
    basket = s.query(sport="Basketball", more=True)
    assert [g["league"] for g in basket["games"]] == ["NBA", "NBA"] and all(g["measured"] is False for g in basket["games"])
    assert {g["sport"] for g in basket["games"]} == {"Basketball"} and basket["measured_min_games"] == 20
    soccer = s.query(sport="Soccer", more=True)
    assert {g["league"] for g in soccer["games"]} == {"Premier League", "Eredivisie"}  # the measured league and the discovered one
    assert all(g["measured"] is True for g in soccer["games"] if g["sport"] == "Soccer")


def test_a_sport_is_measured_at_the_minimum_number_of_scored_games():
    s, _ = service(measured={"Soccer": 19})
    assert s.query()["games"][0]["measured"] is False and s.query()["games"][0]["scored_games"] == 19
    s, _ = service(measured={"Soccer": 20})
    assert s.query()["games"][0]["measured"] is True
    s, _ = service(measured={"Soccer": 5}, MEASURED_MIN_GAMES="5")
    assert s.query()["games"][0]["measured"] is True


def test_with_discovery_off_the_list_is_exactly_the_configured_series():
    s, kalshi = service(SPORTS_DISCOVERY="false")
    assert s.query()["more_sports"] == [] and kalshi.series_calls == 0
    assert [g["title"] for g in s.query(sport="Basketball", more=True)["games"]] == []  # nothing is discovered
    assert s.entry_of("KXNBAGAME") is None and s.entry_of("KXEPLGAME").league == "Premier League"


def test_a_failure_of_the_series_list_is_named_and_the_measured_games_still_show():
    s, kalshi = service()
    kalshi.series_fail = True
    result = s.query()
    assert [g["title"] for g in result["games"]] == ["Coventry vs Newcastle"] and result["more_sports"] == []
    assert any("Other sports could not be discovered" in n for n in result["notes"])


def test_the_sport_and_league_of_any_series_are_known_to_the_runs():
    s, _ = service()
    assert (s.entry_of("KXNBAGAME").sport, s.entry_of("KXNBAGAME").league) == ("Basketball", "NBA")
    assert s.entry_of("KXEPLGAME").sport == "Soccer" and s.entry_of("KXNOPE") is None


class Kalshi:
    """GET /events/{ticker} for the NBA winner and its two companions, as read live on 2026-10-15."""

    def __init__(self, missing=()):
        self.missing = set(missing)

    def get_event(self, ticker):
        from app.kalshi import KalshiNotFound

        if ticker in self.missing:
            raise KalshiNotFound(ticker)
        series = ticker.split("-")[0]
        label = "Over 205.5 points" if series.endswith("TOTAL") else "Los Angeles C wins by over 17.5 points"
        return {"event": {"event_ticker": ticker, "series_ticker": series, "title": ticker},
                "markets": [{"ticker": f"{ticker}-1", "status": "active", "yes_sub_title": label, "floor_strike": 205.5 if series.endswith("TOTAL") else 17.5}]}


def test_the_nba_gets_its_total_points_and_spread_markets_by_the_same_ticker_rule_as_soccer():
    game = GameInfo(event_ticker="KXNBAGAME-26OCT14DENLAC", title="Denver vs Los Angeles C", outcomes=["Denver", "Los Angeles C"],
                    outcome_tickers=["a", "b"], outcome_names=["Denver", "Los Angeles C"], exclusive=True)
    winner = {"event": {"event_ticker": "KXNBAGAME-26OCT14DENLAC", "series_ticker": "KXNBAGAME"}}
    out = attach_companions(game, winner, "Basketball", Kalshi())
    assert [g.kind for g in out.groups] == ["total", "spread"] and out.groups[0].event_ticker == "KXNBATOTAL-26OCT14DENLAC"
    assert out.groups[1].teams == ["Los Angeles C"] and out.group_notes == []
    none = attach_companions(game, winner, "Hockey", Kalshi())  # a sport with no mapped extra markets: winner only
    assert none.groups == []
    gone = attach_companions(game, winner, "Basketball", Kalshi(missing=("KXNBASPREAD-26OCT14DENLAC",)))
    assert [g.kind for g in gone.groups] == ["total"] and any("not offered" in n for n in gone.group_notes)


def test_records_keep_the_sport_and_league_of_their_game():
    game = GameInfo(event_ticker="KX-1", title="A vs B", starts_at="2026-10-13T16:00:00+00:00", outcomes=["A wins", "B wins"],
                    outcome_tickers=["KX-A", "KX-B"], exclusive=True, sport="Basketball", league="NBA")
    records = build_records("run1", game, prediction(), comparison(), None, datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    assert {(r.sport, r.league) for r in records} == {("Basketball", "NBA")}


def test_the_flag_and_the_alert_say_when_the_sport_has_no_scored_results():
    def row_for(scored):
        comp = {"outcomes": comparison()["outcomes"]}
        game = {"run_id": "r", "event_ticker": "KX-1", "title": "A vs B", "start": None, "finished_at": NOW, "prediction": prediction(), "baseline": {}, "forecast_mids": {},
                "sport": "Basketball", "league": "NBA"}
        return build_row(game, comp, load_settings({**ENV}), NOW, scored)

    new = row_for({"Basketball": 3})
    assert new["measured"] is False and any("no scored results yet" in r for r in new["risks"])
    assert row_for({"Basketball": 25})["measured"] is True
    game = {"title": "A vs B", "finished_at": NOW}
    text = alert_text("run_flagged", game, {"supported_claims": 7, "measured": False}, NOW,
                      {"best": {"market": "A wins", "side": "yes", "price": 0.4, "gap": 0.1, "count": 1}})
    assert UNTESTED.strip() in text and UNTESTED.strip() not in alert_text(
        "run_flagged", game, {"supported_claims": 7, "measured": True}, NOW, {"best": {"market": "A wins", "side": "yes", "price": 0.4, "gap": 0.1, "count": 1}})


def test_the_planner_prompt_is_for_any_sport_and_keeps_the_specific_lines():
    text = PLANNER_INSTRUCTIONS
    assert "any sport" in text and "basketball" in text.lower() and "tennis the playing surface" in text and "probable starting pitchers" in text
