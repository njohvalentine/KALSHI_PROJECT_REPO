"""First-half soccer markets (FEAT-20261022-0957): finding them, the three-way first-half winner, the consistency rules, the ranking side. Mocked Kalshi, no network."""

import pytest

from app.research.forecast import InvalidForecast, validate_full
from app.research.markets import COMPANIONS, attach_companions, companion_ticker, group_from_event
from app.research.prompts import GROUP_HEADINGS, GROUP_RULE, forecaster_input
from tests.test_markets import BTTS, NAMES, SPREAD, TOTAL, WINNER, FakeKalshi, answer, market, winner_game

EPL = {"event": {"event_ticker": "KXEPLGAME-26OCT24AVLMCI", "series_ticker": "KXEPLGAME"}}


def ev(part, title, markets):
    return {"event": {"event_ticker": f"KXUCL{part}-26OCT13ATMMUN", "series_ticker": f"KXUCL{part}", "title": title}, "markets": markets}


H1 = ev("1H", "A vs M: First Half Winner", [market("H-A", "Atletico wins 1st Half"), market("H-M", "Manchester United wins 1st Half"), market("H-T", "Tie 1st Half")])
H1TOTAL = ev("1HTOTAL", "A vs M: First Half Total", [market("HT-2", "Over 1.5 1H goals scored", 1.5), market("HT-0", "Over 0.5 1H goals scored", 0.5), market("HT-1", "Over 2.5 1H goals scored", 2.5)])
H1BTTS = ev("1HBTTS", "A vs M: First Half BTTS", [market("HB", "1st Half: Both Teams To Score")])
H1SPREAD = ev("1HSPREAD", "A vs M: First Half Spread", [market("HS-M", "Manchester United wins the 1H by more than 1.5 goals", 1.5), market("HS-A", "Atletico wins the 1H by more than 1.5 goals", 1.5)])
ALL = {"KXUCLTOTAL-26OCT13ATMMUN": TOTAL, "KXUCLBTTS-26OCT13ATMMUN": BTTS, "KXUCLSPREAD-26OCT13ATMMUN": SPREAD, "KXUCL1H-26OCT13ATMMUN": H1,
       "KXUCL1HTOTAL-26OCT13ATMMUN": H1TOTAL, "KXUCL1HBTTS-26OCT13ATMMUN": H1BTTS, "KXUCL1HSPREAD-26OCT13ATMMUN": H1SPREAD}


def game():
    return attach_companions(winner_game(), WINNER, "Soccer", FakeKalshi(ALL))


def test_the_first_half_tickers_follow_the_same_suffix_rule_for_every_league():
    assert dict(COMPANIONS["Soccer"])["h1_winner"] == "1H" and dict(COMPANIONS["Soccer"])["h1_spread"] == "1HSPREAD"
    assert [companion_ticker(EPL["event"], p) for p in ("1H", "1HTOTAL", "1HBTTS", "1HSPREAD")] == [
        "KXEPL1H-26OCT24AVLMCI", "KXEPL1HTOTAL-26OCT24AVLMCI", "KXEPL1HBTTS-26OCT24AVLMCI", "KXEPL1HSPREAD-26OCT24AVLMCI"]
    assert companion_ticker(WINNER["event"], "1H") == "KXUCL1H-26OCT13ATMMUN"  # the Champions League by the same rule


def test_the_kind_names_fit_the_database_column():
    assert all(len(kind) <= 10 for kind, _ in COMPANIONS["Soccer"])  # runs.market_kind is String(10): no migration


def test_the_groups_are_found_and_the_first_half_winner_keeps_kalshis_order_with_each_team_known():
    g = game()
    assert [x.kind for x in g.groups] == ["total", "btts", "spread", "h1_winner", "h1_total", "h1_btts", "h1_spread"] and g.group_notes == []
    winner = next(x for x in g.groups if x.kind == "h1_winner")
    assert winner.tickers == ["H-A", "H-M", "H-T"] and winner.teams == ["Atletico", "Manchester United", None]
    total = next(x for x in g.groups if x.kind == "h1_total")
    assert total.tickers == ["HT-0", "HT-2", "HT-1"][:1] + ["HT-2", "HT-1"] and total.strikes == [0.5, 1.5, 2.5]
    spread = next(x for x in g.groups if x.kind == "h1_spread")
    assert spread.teams == ["Atletico", "Manchester United"]


def test_a_first_half_market_that_is_not_offered_is_noted_and_not_guessed():
    g = attach_companions(winner_game(), WINNER, "Soccer", FakeKalshi({"KXUCL1H-26OCT13ATMMUN": H1}))
    assert [x.kind for x in g.groups] == ["h1_winner"] and "first half total goals: not offered for this game" in g.group_notes
    assert len(g.group_notes) == 6


def test_the_prompt_says_the_first_half_winner_adds_up_and_the_rule_mentions_the_first_half():
    text = forecaster_input(game(), [], "2026-10-13")
    assert "First half: winner (exactly one of these happens" in text and "First half: total goals (each line" in text
    assert "H-A" not in text and "KX" not in text
    assert "First half" in GROUP_HEADINGS["h1_winner"] and "first half" in GROUP_RULE


# order: 1-3 winner; 4-6 total 0.5/1.5/2.5; 7 btts; 8-10 spread (Atletico 1.5, 2.5, United 1.5);
#        11-13 first-half winner (Atletico, United, Tie); 14-16 first-half total 0.5/1.5/2.5; 17 first-half btts; 18-19 first-half spread (Atletico, United)
GOOD = [0.45, 0.30, 0.25, 0.95, 0.80, 0.55, 0.60, 0.20, 0.10, 0.12,
        0.30, 0.20, 0.50, 0.75, 0.40, 0.15, 0.20, 0.03, 0.02]


def check(values):
    return validate_full(game(), answer(values))


def change(**by_position):
    values = list(GOOD)
    for position, value in by_position.items():
        values[int(position[1:]) - 1] = value
    return values


def test_a_consistent_first_half_answer_passes_and_the_first_half_winner_adds_up_to_one():
    probs, notes = check(GOOD)
    assert notes == [] and sum(probs[t] for t in ("H-A", "H-M", "H-T")) == pytest.approx(1.0)
    probs, notes = check(change(p11=0.32, p12=0.21, p13=0.49))  # adds up to 1.02: scaled, not an error
    assert sum(probs[t] for t in ("H-A", "H-M", "H-T")) == pytest.approx(1.0) and probs["H-A"] == pytest.approx(0.32 / 1.02)
    with pytest.raises(InvalidForecast, match="first half.*add up to 1.100"):
        check(change(p11=0.40))  # 0.40 + 0.20 + 0.50


def test_first_half_goals_are_never_more_likely_than_the_full_game_goals_at_the_same_line():
    probs, notes = check(change(p14=0.97))  # over 0.5 in the half 0.97 above over 0.5 in the game 0.95 by 0.02: lowered
    assert probs["HT-0"] == 0.95 and any("full-game goals" in n for n in notes)
    with pytest.raises(InvalidForecast, match="full-game goals"):
        check(change(p14=0.99))  # by 0.04: invalid
    probs, notes = check(change(p16=0.58, p15=0.58))  # over 2.5 and 1.5 in the half above the game's over 2.5 (0.55) by 0.03 or less, same line only
    assert probs["HT-1"] == 0.55


def test_first_half_both_teams_to_score_is_below_the_game_and_below_first_half_over_one_and_a_half():
    probs, notes = check(change(p17=0.42))  # above first-half over 1.5 (0.40) by 0.02
    assert probs["HB"] == 0.40 and any("first-half both teams" in n for n in notes)
    with pytest.raises(InvalidForecast, match="first-half both teams"):
        check(change(p17=0.70))
    probs, notes = check(change(p7=0.18, p4=0.95, p5=0.80))  # game btts 0.18, first-half btts 0.20
    assert probs["HB"] == 0.18


def test_a_teams_first_half_margin_is_below_that_teams_first_half_win_and_a_half_win_is_not_capped_by_the_game_win():
    probs, notes = check(change(p18=0.32))  # Atletico by 1.5 in the half 0.32 above Atletico wins the half 0.30
    assert probs["HS-A"] == pytest.approx(0.30, abs=1e-9) and any("h1_spread" in n for n in notes)
    probs, notes = check(change(p1=0.20, p2=0.55, p3=0.25))  # Atletico wins the game 0.20 but the half 0.30: fine
    assert notes == [] and probs["H-A"] == pytest.approx(0.30)


def test_first_half_lines_are_ordered_like_the_other_lines():
    probs, notes = check(change(p16=0.42))  # over 2.5 in the half above over 1.5 by 0.02
    assert probs["HT-1"] == 0.40 and any("higher line" in n for n in notes)


def test_the_ranking_treats_the_first_half_winner_like_a_match_result():
    from app.ranking import EXCLUSIVE_KINDS
    assert EXCLUSIVE_KINDS == ("winner", "h1_winner")
