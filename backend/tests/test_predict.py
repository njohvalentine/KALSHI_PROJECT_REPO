import pytest

from app.research.forecast import ForecastSet, ValidForecast
from app.research.predict import build_prediction
from app.research.schemas import GameInfo

GAME = GameInfo(event_ticker="KX-1", title="A vs B", outcomes=["A wins", "Tie is the result", "B wins"],
                outcome_tickers=["KX-A", "KX-T", "KX-B"], exclusive=True)
TOTALS = GameInfo(event_ticker="KX-2", title="Totals", outcomes=["Over 1.5", "Over 2.5"], outcome_tickers=["O15", "O25"], exclusive=False)


def vf(index, variant, a, t, b):
    return ValidForecast(index, variant, {"KX-A": a, "KX-T": t, "KX-B": b}, "why", "gpt-5.4")


def fset(*forecasts, dropped=(), evidence="supported"):
    return ForecastSet(forecasts=list(forecasts), dropped=list(dropped), evidence=evidence)


def by_ticker(prediction):
    return {o["market_ticker"]: o for o in prediction["outcomes"]}


def test_median_spread_min_max_and_each_forecast_per_outcome():
    p = build_prediction(GAME, fset(vf(0, "evidence_first", 0.50, 0.25, 0.25), vf(1, "base_rate_first", 0.40, 0.30, 0.30),
                                    vf(2, "devils_advocate", 0.60, 0.20, 0.20)), supported_claims=7)
    a = by_ticker(p)["KX-A"]
    assert (a["probability"], a["min"], a["max"], a["spread"], a["median_raw"]) == (0.5, 0.4, 0.6, 0.2, 0.5)
    assert [f["variant"] for f in a["forecasts"]] == ["evidence_first", "base_rate_first", "devils_advocate"]
    assert a["outcome"] == "A wins"
    assert (p["forecasters_valid"], p["supported_claims"], p["evidence"], p["dropped"]) == (3, 7, "supported", [])


def test_one_odd_forecaster_does_not_move_the_median():
    p = build_prediction(GAME, fset(vf(0, "a", 0.50, 0.30, 0.20), vf(1, "b", 0.52, 0.28, 0.20), vf(2, "c", 0.05, 0.05, 0.90)), 5)
    assert by_ticker(p)["KX-A"]["probability"] == pytest.approx(0.5, abs=0.03)  # after scaling to 100%


def test_two_valid_forecasts_use_their_mean():
    p = build_prediction(GAME, fset(vf(0, "a", 0.60, 0.20, 0.20), vf(1, "b", 0.40, 0.30, 0.30)), 5)
    o = by_ticker(p)
    assert o["KX-A"]["median_raw"] == 0.5 and o["KX-T"]["median_raw"] == 0.25 and p["forecasters_valid"] == 2


def test_medians_are_scaled_to_one_when_exactly_one_outcome_happens_and_the_raw_median_is_kept():
    # each vector adds up to 1, but the medians (0.50, 0.30, 0.30) add up to 1.10
    p = build_prediction(GAME, fset(vf(0, "a", 0.50, 0.30, 0.20), vf(1, "b", 0.40, 0.30, 0.30), vf(2, "c", 0.30, 0.40, 0.30)), 5)
    o = by_ticker(p)
    assert o["KX-A"]["median_raw"] == 0.4 and o["KX-T"]["median_raw"] == 0.3 and o["KX-B"]["median_raw"] == 0.3
    assert sum(x["probability"] for x in p["outcomes"]) == pytest.approx(1.0, abs=0.0005)
    assert o["KX-A"]["probability"] == pytest.approx(0.4, abs=0.0005)


def test_medians_are_not_scaled_for_non_exclusive_markets():
    f = [ValidForecast(i, v, {"O15": a, "O25": b}, "why", "m") for i, (v, a, b) in enumerate([("a", .8, .5), ("b", .7, .4), ("c", .9, .6)])]
    o = by_ticker(build_prediction(TOTALS, fset(*f), 5))
    assert o["O15"]["probability"] == 0.8 and o["O25"]["probability"] == 0.5


def test_no_prediction_with_fewer_than_two_forecasts_and_the_reason_is_kept():
    dropped = [{"index": 1, "variant": "b", "reason": "call failed: RuntimeError"}, {"index": 2, "variant": "c", "reason": "sum 0.9"}]
    p = build_prediction(GAME, fset(vf(0, "a", 0.5, 0.3, 0.2), dropped=dropped), 5)
    assert "outcomes" not in p and "Only 1 valid forecast(s)" in p["unavailable"] and "call failed" in p["unavailable"]
    assert p["dropped"] == dropped and p["forecasters_valid"] == 1


def test_evidence_none_is_carried_through():
    p = build_prediction(GAME, fset(vf(0, "a", .5, .3, .2), vf(1, "b", .5, .3, .2), evidence="none"), 0)
    assert p["evidence"] == "none" and p["supported_claims"] == 0
