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


def run(o, m, fee=FEE, evidence="supported", claims=7, settings=S):
    return compare_outcome(o, m, fee, evidence, claims, settings)


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
    r = run(outcome(0.20, 0.15, 0.25), market())
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
    strict = load_settings(BASE | {"EDGE_MIN": "0.2"})
    assert run(outcome(), market(), settings=strict)["meaningful"] is False
    with pytest.raises(Exception, match="EDGE_MIN"):
        load_settings(BASE | {"EDGE_MIN": "1.5"})


PREDICTION = {"evidence": "supported", "supported_claims": 7, "forecasters_valid": 3, "dropped": [], "outcomes": [outcome()]}
EVENT = {"event": {"series_ticker": "KXTEST"}, "markets": [market()]}


def test_compare_returns_plain_json_with_the_time_the_fee_and_the_thresholds():
    c = compare(PREDICTION, EVENT, FEE, S, NOW)
    assert c["priced_at"] == NOW.isoformat() and c["fee"] == {"fee_type": "quadratic", "multiplier": 1.0, "source": "series"}
    assert c["thresholds"] == {"edge_min": 0.05, "min_supported_claims": 5, "min_ask_size": 10.0}
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
