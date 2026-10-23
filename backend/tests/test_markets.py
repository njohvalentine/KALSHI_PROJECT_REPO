"""Companion markets: finding them, the forecast prompt with them, and the checks between related markets."""

import asyncio
import logging
from dataclasses import asdict

import pytest

from app.config import load_settings
from app.kalshi import KalshiError, KalshiNotFound
from app.research.forecast import ForecastAnswer, InvalidForecast, OutcomeProbability, run_forecasters, validate_full
from app.research.markets import attach_companions, companion_ticker, group_from_event
from app.research.predict import build_prediction
from app.research.prompts import GROUP_RULE, forecaster_input, planner_input
from app.research.schemas import GameInfo, MarketGroup, Usage

BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40, "OPENAI_API_KEY": "sk-test"}
S = load_settings(BASE)

WINNER = {"event": {"event_ticker": "KXUCLGAME-26OCT13ATMMUN", "series_ticker": "KXUCLGAME"}}


def market(ticker, title, strike=None, status="active"):
    return {"ticker": ticker, "yes_sub_title": title, "title": title, "floor_strike": strike, "status": status}


TOTAL = {"event": {"event_ticker": "KXUCLTOTAL-26OCT13ATMMUN", "series_ticker": "KXUCLTOTAL", "title": "A vs M: Total Goals"}, "markets": [
    market("T-3", "Over 2.5 goals scored", 2.5), market("T-1", "Over 0.5 goals scored", 0.5), market("T-2", "Over 1.5 goals scored", 1.5),
    market("T-9", "Over 8.5 goals scored", 8.5, status="closed")]}
BTTS = {"event": {"event_ticker": "KXUCLBTTS-26OCT13ATMMUN", "series_ticker": "KXUCLBTTS", "title": "A vs M: BTTS"}, "markets": [market("B", "Both Teams To Score")]}
SPREAD = {"event": {"event_ticker": "KXUCLSPREAD-26OCT13ATMMUN", "series_ticker": "KXUCLSPREAD", "title": "A vs M: Spread"}, "markets": [
    market("S-M2", "Manchester United wins by more than 1.5 goals", 1.5), market("S-A3", "Atletico wins by more than 2.5 goals", 2.5),
    market("S-A2", "Atletico wins by more than 1.5 goals", 1.5)]}
NAMES = ["Atletico", "Manchester United", "Tie"]


def winner_game(**kw):
    return GameInfo(event_ticker="KXUCLGAME-26OCT13ATMMUN", title="Atletico vs Manchester United", starts_at="2026-10-13T19:00:00+00:00",
                    outcomes=["Atletico wins", "Manchester United wins", "Tie is the result"], outcome_tickers=["W-A", "W-M", "W-T"],
                    outcome_names=NAMES, exclusive=True, **kw)


class FakeKalshi:
    def __init__(self, events=None, errors=None):
        self.events, self.errors, self.calls = events or {}, errors or {}, []

    def get_event(self, ticker):
        self.calls.append(ticker)
        if ticker in self.errors:
            raise self.errors[ticker]
        if ticker not in self.events:
            raise KalshiNotFound("404")
        return self.events[ticker]


def test_the_companion_ticker_shares_the_games_suffix():
    assert companion_ticker(WINNER["event"], "TOTAL") == "KXUCLTOTAL-26OCT13ATMMUN"
    assert companion_ticker({"series_ticker": "KXMLBGAME", "event_ticker": "KXMLBGAME-26OCT132000CLETB"}, "SPREAD") == "KXMLBSPREAD-26OCT132000CLETB"
    assert companion_ticker({"series_ticker": "KXATPMATCH", "event_ticker": "KXATPMATCH-26OCT13HURDAV"}, "TOTAL") is None  # not a GAME series
    assert companion_ticker({"series_ticker": "KXUCLGAME", "event_ticker": "NODASH"}, "TOTAL") is None


def test_a_group_has_open_markets_only_in_line_order_and_spread_markets_know_their_team():
    total = group_from_event("total", TOTAL, NAMES)
    assert total.tickers == ["T-1", "T-2", "T-3"] and total.strikes == [0.5, 1.5, 2.5] and total.teams == [None] * 3  # the closed line is left out
    spread = group_from_event("spread", SPREAD, NAMES)
    assert spread.teams == ["Atletico", "Atletico", "Manchester United"] and spread.strikes == [1.5, 2.5, 1.5]
    assert group_from_event("btts", BTTS, NAMES).tickers == ["B"]
    assert group_from_event("total", {"event": {}, "markets": [market("X", "x", 1.5, status="closed")]}, NAMES) is None


def test_attach_finds_what_exists_and_notes_what_does_not(caplog):
    kalshi = FakeKalshi({"KXUCLTOTAL-26OCT13ATMMUN": TOTAL, "KXUCLSPREAD-26OCT13ATMMUN": SPREAD}, errors={"KXUCLBTTS-26OCT13ATMMUN": KalshiError("down")})
    with caplog.at_level(logging.WARNING):
        game = attach_companions(winner_game(), WINNER, "Soccer", kalshi)
    assert [g.kind for g in game.groups] == ["total", "spread"] and game.market_tickers[:3] == ["W-A", "W-M", "W-T"]
    assert game.group_notes[0] == "both teams to score: could not be read from Kalshi" and "KXUCLBTTS" in caplog.text
    assert game.group_notes[1:] == [f"{k}: not offered for this game" for k in ("first half winner", "first half total goals", "first half both teams to score", "first half margin of victory")]
    missing = attach_companions(winner_game(), WINNER, "Soccer", FakeKalshi())
    assert missing.groups == [] and len(missing.group_notes) == 7 and "not offered for this game" in missing.group_notes[0]


def test_baseball_has_no_btts_and_unknown_sports_are_left_alone():
    kalshi = FakeKalshi()
    attach_companions(winner_game(), {"event": {"event_ticker": "KXMLBGAME-26X", "series_ticker": "KXMLBGAME"}}, "Baseball", kalshi)
    assert kalshi.calls == ["KXMLBTOTAL-26X", "KXMLBSPREAD-26X"]
    kalshi = FakeKalshi()
    assert attach_companions(winner_game(), WINNER, "Tennis", kalshi).groups == [] and kalshi.calls == []
    assert attach_companions(winner_game(), WINNER, None, kalshi).group_notes == []


def full_game():
    return attach_companions(winner_game(), WINNER, "Soccer", FakeKalshi(
        {"KXUCLTOTAL-26OCT13ATMMUN": TOTAL, "KXUCLBTTS-26OCT13ATMMUN": BTTS, "KXUCLSPREAD-26OCT13ATMMUN": SPREAD}))


def test_the_game_survives_being_stored_as_plain_data():
    game = full_game()
    again = GameInfo(**asdict(game))
    assert again == game and isinstance(again.groups[0], MarketGroup) and again.kind_of("B") == "btts" and again.kind_of("W-A") == "winner"


def test_the_prompt_numbers_every_market_in_groups_and_carries_no_prices():
    text = forecaster_input(full_game(), [], "2026-10-13")
    assert "1. Atletico wins" in text and "3. Tie is the result" in text
    assert "Total goals, runs or points (each line is a separate yes or no question about this game):\n4. Over 0.5 goals scored\n5. Over 1.5" in text
    assert "7. Both Teams To Score" in text and "Both teams to score (each line" in text and "Margin of victory" in text
    assert "8. Atletico wins by more than 1.5 goals" in text and "10. Manchester United wins by more than 1.5 goals" in text
    assert "KX" not in text and "¢" not in text
    assert "scoring" in planner_input(full_game(), "2026-10-13") and "scoring" not in planner_input(winner_game(), "2026-10-13")
    assert "Give each its own probability" in GROUP_RULE


def answer(values):
    return ForecastAnswer(probabilities=[OutcomeProbability(outcome_number=i, probability=p) for i, p in enumerate(values, 1)], reasoning="x")


# order: 1-3 winner (Atletico, United, Tie); 4-6 totals 0.5, 1.5, 2.5; 7 BTTS; 8-10 spread Atletico 1.5, 2.5, United 1.5 (alphabetical by team)
GOOD = [0.45, 0.30, 0.25, 0.95, 0.80, 0.55, 0.60, 0.20, 0.10, 0.12]


def test_a_consistent_answer_passes_unchanged_and_only_the_winner_outcomes_add_up_to_one():
    probs, notes = validate_full(full_game(), answer(GOOD))
    assert notes == [] and probs["T-2"] == 0.80 and probs["B"] == 0.60 and probs["W-A"] == pytest.approx(0.45)
    assert sum(probs[t] for t in ("W-A", "W-M", "W-T")) == pytest.approx(1.0)
    with pytest.raises(InvalidForecast, match="exclusive but the probabilities add up to 1.100"):
        validate_full(full_game(), answer([0.55, 0.30, 0.25] + GOOD[3:]))  # the winner outcomes must add up; the other markets need not


def test_the_answer_must_cover_every_market_of_the_game():
    with pytest.raises(InvalidForecast, match="expected one probability for each outcome 1..10"):
        validate_full(full_game(), answer(GOOD[:9]))


def test_small_inconsistencies_are_lowered_and_reported_and_large_ones_make_the_answer_invalid():
    probs, notes = validate_full(full_game(), answer([0.45, 0.30, 0.25, 0.95, 0.80, 0.82, 0.60, 0.20, 0.10, 0.12]))  # over 2.5 above over 1.5 by 0.02
    assert probs["T-3"] == 0.80 and notes == ["total: a higher line is more likely than a lower one: lowered by 0.020"]
    with pytest.raises(InvalidForecast, match="total: a higher line is more likely than a lower one"):
        validate_full(full_game(), answer([0.45, 0.30, 0.25, 0.95, 0.60, 0.80, 0.60, 0.20, 0.10, 0.12]))  # by 0.20


def test_spread_lines_win_probability_and_btts_are_checked_against_each_other():
    probs, notes = validate_full(full_game(), answer([0.45, 0.30, 0.25, 0.95, 0.80, 0.55, 0.60, 0.20, 0.22, 0.12]))  # Atletico by 2.5 above by 1.5
    assert probs["S-A3"] == 0.20 and len(notes) == 1
    probs, notes = validate_full(full_game(), answer([0.20, 0.55, 0.25, 0.95, 0.80, 0.55, 0.60, 0.21, 0.10, 0.12]))  # Atletico wins 0.20, by 1.5 0.21
    assert probs["S-A2"] == pytest.approx(0.20, abs=1e-9) and "spread: winning by a margin" in notes[0]
    probs, notes = validate_full(full_game(), answer([0.45, 0.30, 0.25, 0.95, 0.60, 0.50, 0.62, 0.20, 0.10, 0.12]))  # btts 0.62 above over 1.5 0.60
    assert probs["B"] == 0.60 and "btts" in notes[0]
    with pytest.raises(InvalidForecast, match="btts"):
        validate_full(full_game(), answer([0.45, 0.30, 0.25, 0.95, 0.60, 0.50, 0.90, 0.20, 0.10, 0.12]))


class FakeForecaster:
    def __init__(self, values):
        self.values = values

    async def forecast(self, game, claims, framing):
        return answer(self.values), Usage("gpt-5.4", 1, 0, 1)


def test_prediction_has_a_kind_for_each_market_the_adjustments_and_the_markets_not_offered():
    game = attach_companions(winner_game(), WINNER, "Soccer", FakeKalshi({"KXUCLTOTAL-26OCT13ATMMUN": TOTAL, "KXUCLSPREAD-26OCT13ATMMUN": SPREAD}))
    values = [0.45, 0.30, 0.25, 0.95, 0.80, 0.82, 0.20, 0.10, 0.12]  # over 2.5 slightly above over 1.5
    forecast_set = asyncio.run(run_forecasters(game, [{"angle": "Form", "text": "A fact"}], FakeForecaster(values), S))
    p = build_prediction(game, forecast_set, 1)
    assert [o["kind"] for o in p["outcomes"]] == ["winner"] * 3 + ["total"] * 3 + ["spread"] * 3
    assert sum(o["probability"] for o in p["outcomes"] if o["kind"] == "winner") == pytest.approx(1.0, abs=0.001)
    assert next(o for o in p["outcomes"] if o["market_ticker"] == "T-3")["probability"] == 0.80
    assert p["markets_not_offered"][0] == "both teams to score: not offered for this game" and len(p["markets_not_offered"]) == 5
    assert len(p["adjustments"]) == 3 and p["adjustments"][0]["note"].startswith("total:")
