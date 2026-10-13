import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.config import load_settings
from app.kalshi import KalshiError
from app.research.compare import (
    ASSUMED_FEE, FeeInfo, compare, compare_outcome, compare_run, fee_info_from_series, fee_per_contract,
)

BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
S = load_settings(BASE)
FEE = FeeInfo("quadratic", Decimal(1), "series")
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def outcome(p=0.55, lo=0.50, hi=0.60, ticker="KX-A"):
    return {"market_ticker": ticker, "outcome": "A wins", "probability": p, "min": lo, "max": hi}


def market(bid="0.40", ask="0.42", no_ask=None, ask_size="100", bid_size="80", ticker="KX-A"):
    m = {"ticker": ticker, "yes_bid_dollars": bid, "yes_ask_dollars": ask, "yes_ask_size_fp": ask_size, "yes_bid_size_fp": bid_size}
    if no_ask is not None:
        m["no_ask_dollars"] = no_ask
    return m


def run(o, m, fee=FEE, evidence="supported", claims=7, settings=S, baseline="auto"):
    if baseline == "auto":  # the plain AI call said 0.10 closer to even than we did, so the research moved us toward the gap
        baseline = o["probability"] - 0.10 if o["probability"] >= 0.5 else o["probability"] + 0.10
    return compare_outcome(o, m, fee, evidence, claims, settings, baseline)


@pytest.mark.parametrize("price,multiplier,expected", [
    ("0.50", 1, "0.0175"), ("0.50", "0.5", "0.00875"), ("0.10", 1, "0.0063"), ("0.90", 1, "0.0063"), ("0.42", 1, "0.017052"),
])
def test_fee_formula(price, multiplier, expected):
    assert fee_per_contract(Decimal(price), FeeInfo("quadratic", Decimal(str(multiplier)), "series")) == Decimal(expected)


def test_fee_info_comes_from_the_series_and_unknown_values_are_marked_assumed():
    assert fee_info_from_series({"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 0.5}) == FeeInfo("quadratic_with_maker_fees", Decimal("0.5"), "series")
    for bad in ({"fee_type": "flat", "fee_multiplier": 1}, {"fee_type": "quadratic"}, {"fee_type": "quadratic", "fee_multiplier": "x"},
                {"fee_type": "quadratic", "fee_multiplier": 0}, {}):
        info = fee_info_from_series(bad)
        assert info.source.startswith("assumed") and (info.fee_type, info.multiplier) == ("quadratic", Decimal(1))


def test_yes_side_net_edge_fee_worst_case_and_a_meaningful_gap():
    r = run(outcome(), market())
    assert r["side"] == "yes" and r["yes"]["price"] == Decimal("0.42")
    assert r["net_edge"] == Decimal("0.55") - Decimal("0.42") - Decimal("0.017052")
    assert r["worst_case_edge"] == Decimal("0.50") - Decimal("0.42") - Decimal("0.017052")
    assert r["meaningful"] is True and r["reasons"] == []


def test_the_no_side_is_chosen_when_it_has_the_larger_edge_and_uses_the_lowest_forecaster_view():
    # we think A wins only 20% (range 15 to 25%); the market asks 0.42 for yes, so NO costs 0.60 (1 - bid 0.40)
    r = run(outcome(0.20, 0.15, 0.25), market(), settings=load_settings(BASE | {"EDGE_PLAUSIBLE_MAX": "0.5"}))
    assert r["side"] == "no" and r["no"]["price"] == Decimal("0.60")
    assert r["net_edge"] == Decimal("0.80") - Decimal("0.60") - fee_per_contract(Decimal("0.60"), FEE)
    assert r["worst_case_edge"] == Decimal("0.75") - Decimal("0.60") - fee_per_contract(Decimal("0.60"), FEE)  # 1 - max forecast
    assert r["no"]["size"] == Decimal("80")  # contracts at the best YES bid are the ones at the NO ask
    assert r["meaningful"] is True


def test_no_ask_is_one_minus_the_yes_bid_when_kalshi_does_not_send_it():
    assert run(outcome(), market(bid="0.40"))["no_ask"] == Decimal("0.60")
    assert run(outcome(), market(bid="0.40", no_ask="0.61"))["no_ask"] == Decimal("0.61")  # its own field wins when present


@pytest.mark.parametrize("m", [market(ask="0.0000", bid="0.0000"), market(ask="1.0000", bid="1.0000"), market(ask=None, bid=None)])
def test_an_empty_book_has_no_executable_price_and_is_never_compared(m):
    r = run(outcome(), m)
    assert r["side"] is None and r["meaningful"] is False and r["net_edge"] is None
    assert r["reasons"] == ["no executable price (no ask on either side)"]


def test_a_missing_side_is_skipped_but_the_other_is_still_compared():
    r = run(outcome(), market(ask=None, bid="0.40"))  # nobody sells YES
    assert r["yes"] is None and r["side"] == "no"


def test_missing_market_is_reported():
    assert run(outcome(), None)["reasons"] == ["Kalshi returned no market for this outcome"]


@pytest.mark.parametrize("o,m,kwargs,reason", [
    (outcome(0.45, 0.40, 0.50), market(), {}, "below EDGE_MIN"),                                  # edge too small
    (outcome(0.55, 0.40, 0.60), market(), {}, "least favourable forecaster shows no edge"),      # one forecaster sees no edge
    (outcome(), market(), {"evidence": "none", "claims": 0}, "no supported evidence"),
    (outcome(), market(), {"claims": 3}, "only 3 supported claims (MIN_SUPPORTED_CLAIMS is 5)"),
    (outcome(), market(ask_size="4"), {}, "only 4 contracts at the best price"),
    (outcome(), market(ask_size=None), {}, "an unknown number of contracts"),
])
def test_each_condition_can_fail_alone_and_is_named(o, m, kwargs, reason):
    r = run(o, m, **kwargs)
    assert r["meaningful"] is False and any(reason in x for x in r["reasons"])
    if "below EDGE_MIN" not in reason and "no edge" not in reason:
        assert len(r["reasons"]) == 1  # only that condition failed


def test_thresholds_are_settings():
    strict = load_settings(BASE | {"EDGE_MIN": "0.1", "EDGE_PLAUSIBLE_MAX": "0.5", "MIN_RESEARCH_SHIFT": "0.5"})
    assert run(outcome(), market(), settings=strict)["meaningful"] is False  # the shift of 0.10 is below the 0.5 asked for
    with pytest.raises(Exception, match="EDGE_MIN"):
        load_settings(BASE | {"EDGE_MIN": "1.5"})
    with pytest.raises(Exception, match="EDGE_PLAUSIBLE_MAX must be larger than EDGE_MIN"):
        load_settings(BASE | {"EDGE_MIN": "0.2"})  # the default plausibility limit is 0.15
    with pytest.raises(Exception, match="MIN_RESEARCH_SHIFT"):
        load_settings(BASE | {"MIN_RESEARCH_SHIFT": "2"})


PREDICTION = {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [outcome()]}
EVENT = {"event": {"series_ticker": "KXTEST"}, "markets": [market()]}


def test_compare_returns_plain_json_with_the_time_the_fee_and_the_thresholds():
    c = compare(PREDICTION, EVENT, FEE, S, NOW, baseline={"KX-A": 0.45})
    assert c["priced_at"] == NOW.isoformat() and c["fee"] == {"fee_type": "quadratic", "multiplier": 1.0, "source": "series"}
    assert c["thresholds"] == {"edge_min": 0.05, "min_supported_claims": 5, "min_ask_size": 10.0, "min_research_shift": 0.05, "edge_plausible_max": 0.15}
    o = c["outcomes"][0]
    assert isinstance(o["net_edge"], float) and o["yes"]["price"] == 0.42 and o["meaningful"] is True
    import json
    json.dumps(c)  # fully serialisable


class FakeKalshi:
    def __init__(self, event=EVENT, series=None, event_error=None, series_error=None):
        self.event, self.series, self.event_error, self.series_error, self.calls = event, series, event_error, series_error, []

    def get_event(self, ticker):
        self.calls.append(("event", ticker))
        if self.event_error:
            raise self.event_error
        return self.event

    def get_series(self, ticker):
        self.calls.append(("series", ticker))
        if self.series_error:
            raise self.series_error
        return {"series": self.series}


def test_compare_run_reads_fresh_prices_and_the_series_fee():
    k = FakeKalshi(series={"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 0.5})
    c = asyncio.run(compare_run(k, "KX-1", PREDICTION, S))
    assert k.calls == [("event", "KX-1"), ("series", "KXTEST")] and c["fee"]["multiplier"] == 0.5 and c["fee"]["source"] == "series"


def test_an_unreadable_series_uses_the_assumed_fee_and_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        c = asyncio.run(compare_run(FakeKalshi(series_error=KalshiError("boom")), "KX-1", PREDICTION, S))
    assert c["fee"]["source"] == "assumed: the series could not be read" and c["fee"]["multiplier"] == 1.0
    assert "assuming quadratic" in caplog.text


def test_an_event_without_a_series_ticker_uses_the_assumed_fee_and_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        c = asyncio.run(compare_run(FakeKalshi(event={"event": {}, "markets": [market()]}), "KX-1", PREDICTION, S))
    assert c["fee"]["source"] == "assumed: the event has no series ticker" and "no series ticker" in caplog.text


def test_unreadable_prices_give_a_reason_not_an_exception():
    c = asyncio.run(compare_run(FakeKalshi(event_error=KalshiError("down")), "KX-1", PREDICTION, S))
    assert c == {"unavailable": "Kalshi prices could not be read: down"}


def test_no_prediction_means_nothing_to_compare_and_no_kalshi_call():
    k = FakeKalshi()
    assert asyncio.run(compare_run(k, "KX-1", {"unavailable": "x"}, S)) == {"unavailable": "There is no prediction to compare."}
    assert k.calls == []


def test_nested_markets_in_the_event_are_also_read():
    event = {"event": {"series_ticker": "KXTEST", "markets": [market()]}}
    assert compare(PREDICTION, event, FEE, S, NOW)["outcomes"][0]["side"] == "yes"


def test_markets_of_other_events_are_compared_with_their_own_fee():
    prediction = {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [
        outcome(0.55, 0.50, 0.60), {**outcome(0.70, 0.65, 0.75, ticker="T-2"), "kind": "total"}]}
    total_event = {"event": {"series_ticker": "KXTTOTAL"}, "markets": [market(ticker="T-2", bid="0.50", ask="0.52")]}
    half = FeeInfo("quadratic_with_maker_fees", Decimal("0.5"), "series")
    c = compare(prediction, EVENT, FEE, S, NOW, companions=[(total_event, half)])
    winner, total = c["outcomes"]
    assert winner["fee"]["multiplier"] == 1.0 and total["fee"] == {"fee_type": "quadratic_with_maker_fees", "multiplier": 0.5, "source": "series"}
    assert total["yes_ask"] == 0.52 and total["side"] == "yes"
    assert total["net_edge"] == pytest.approx(0.70 - 0.52 - 0.07 * 0.5 * 0.52 * 0.48, abs=1e-5)
    assert c["fee"]["multiplier"] == 1.0  # the top-level fee stays the winner event's


class FakeKalshiMany:
    def __init__(self, events, series, event_errors=()):
        self.events, self.series, self.event_errors, self.calls = events, series, set(event_errors), []

    def get_event(self, ticker):
        self.calls.append(("event", ticker))
        if ticker in self.event_errors:
            raise KalshiError("down")
        return self.events[ticker]

    def get_series(self, ticker):
        self.calls.append(("series", ticker))
        return {"series": self.series[ticker]}


def test_compare_run_reads_each_companion_event_and_each_series_fee_once():
    prediction = {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [
        outcome(0.55, 0.50, 0.60), {**outcome(0.70, 0.65, 0.75, ticker="T-2"), "kind": "total"}, {**outcome(0.30, 0.25, 0.35, ticker="S-1"), "kind": "spread"}]}
    events = {
        "KX-1": EVENT,
        "KXTTOTAL-1": {"event": {"series_ticker": "KXTTOTAL"}, "markets": [market(ticker="T-2", bid="0.50", ask="0.52")]},
        "KXTSPREAD-1": {"event": {"series_ticker": "KXTTOTAL"}, "markets": [market(ticker="S-1", bid="0.20", ask="0.22")]},  # same series as the total
    }
    k = FakeKalshiMany(events, {"KXTEST": {"fee_type": "quadratic", "fee_multiplier": 1}, "KXTTOTAL": {"fee_type": "quadratic_with_maker_fees", "fee_multiplier": 0.5}})
    c = asyncio.run(compare_run(k, "KX-1", prediction, S, companions=[("KXTTOTAL-1", "KXTTOTAL"), ("KXTSPREAD-1", "KXTTOTAL")]))
    assert [o["fee"]["multiplier"] for o in c["outcomes"]] == [1.0, 0.5, 0.5]
    assert [x for x in k.calls if x[0] == "series"] == [("series", "KXTEST"), ("series", "KXTTOTAL")]  # the shared series was read once


def test_a_companion_event_that_cannot_be_read_leaves_its_markets_without_a_price_and_the_rest_intact():
    prediction = {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [
        outcome(0.55, 0.50, 0.60), {**outcome(0.70, 0.65, 0.75, ticker="T-2"), "kind": "total"}]}
    k = FakeKalshiMany({"KX-1": EVENT}, {"KXTEST": {"fee_type": "quadratic", "fee_multiplier": 1}}, event_errors=["KXTTOTAL-1"])
    c = asyncio.run(compare_run(k, "KX-1", prediction, S, companions=[("KXTTOTAL-1", "KXTTOTAL")]))
    assert c["outcomes"][0]["side"] == "yes" and c["outcomes"][1]["reasons"] == ["Kalshi returned no market for this outcome"]


def test_the_research_must_move_the_forecast_toward_the_gap_on_the_side_we_would_buy():
    o, m = outcome(0.55, 0.50, 0.60), market()  # buying yes at 0.42
    assert run(o, m, baseline=0.45)["meaningful"] is True and run(o, m, baseline=0.45)["research_shift"] == Decimal("0.10")
    moved_toward_the_market = run(o, m, baseline=0.62)  # the plain AI call was even further from the market than us
    assert moved_toward_the_market["meaningful"] is False and moved_toward_the_market["research_shift"] == Decimal("-0.07")
    assert any("did not move the forecast toward the gap (shift -0.070, needs 0.05)" in r for r in moved_toward_the_market["reasons"])
    small = run(o, m, baseline=0.52)
    assert small["meaningful"] is False and len(small["reasons"]) == 1
    # buying no: the research must have moved our probability DOWN from the baseline
    no_side = outcome(0.20, 0.15, 0.25)
    relaxed = load_settings(BASE | {"EDGE_PLAUSIBLE_MAX": "0.5"})
    assert run(no_side, m, baseline=0.30, settings=relaxed)["meaningful"] is True
    assert run(no_side, m, baseline=0.10, settings=relaxed)["meaningful"] is False  # moved up, toward "yes", away from the gap on "no"


def test_without_a_plain_ai_call_nothing_is_flagged_and_it_says_why():
    r = run(outcome(), market(), baseline=None)
    assert r["meaningful"] is False and r["research_shift"] is None and r["reasons"] == ["no plain AI call to compare with"]


def test_a_gap_above_the_plausibility_limit_is_not_flagged_as_an_opportunity():
    r = run(outcome(0.80, 0.75, 0.85), market(bid="0.40", ask="0.42"))  # net edge about 0.35
    assert r["meaningful"] is False and r["reasons"] == ["gap above 0.15 is more likely a model error than an opportunity"]
