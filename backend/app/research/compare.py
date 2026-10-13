"""Compares our probabilities with the price a bet can really be placed at.

Executable price: buy YES at the YES ask, buy NO at the NO ask (1 minus the YES bid). A side with no
ask has no executable price and is never compared. Fees: taker fee for one contract at price P is
0.07 x multiplier x P x (1 - P), the formula Kalshi publishes for `quadratic` fee types (confirmed
only from secondary sources until Kalshi's own schedule can be read; see the spec). The fee type and
multiplier come from the game's series. If they cannot be read, the assumed values are used and
marked, never silently.

A "meaningful gap" is only a flag for a person to look; the thresholds are placeholders until
Milestone 4 has scored real forecasts."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.config import Settings
from app.kalshi import KalshiClient, KalshiError

log = logging.getLogger("app.research.compare")

FEE_RATE = Decimal("0.07")
ONE = Decimal(1)
KNOWN_FEE_TYPES = ("quadratic", "quadratic_with_maker_fees")


@dataclass(frozen=True)
class FeeInfo:
    fee_type: str
    multiplier: Decimal
    source: str  # "series" or "assumed: <why>"


ASSUMED_FEE = FeeInfo("quadratic", ONE, "assumed")


def fee_per_contract(price: Decimal, fee: FeeInfo) -> Decimal:
    """Taker fee for one contract, in dollars, not rounded (Kalshi rounds up per order, which depends on size)."""
    return FEE_RATE * fee.multiplier * price * (ONE - price)


def fee_info_from_series(series: dict) -> FeeInfo:
    fee_type, multiplier = series.get("fee_type"), series.get("fee_multiplier")
    if fee_type not in KNOWN_FEE_TYPES:
        return FeeInfo(ASSUMED_FEE.fee_type, ASSUMED_FEE.multiplier, f"assumed: unknown fee type {fee_type!r}")
    try:
        value = Decimal(str(multiplier))
    except InvalidOperation:
        return FeeInfo(ASSUMED_FEE.fee_type, ASSUMED_FEE.multiplier, f"assumed: unreadable fee multiplier {multiplier!r}")
    if value <= 0:
        return FeeInfo(ASSUMED_FEE.fee_type, ASSUMED_FEE.multiplier, f"assumed: unusable fee multiplier {multiplier!r}")
    return FeeInfo(fee_type, value, "series")


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def _price(value) -> Decimal | None:
    """A usable ask: strictly between 0 and 1 dollar. 0 or 1 means an empty book."""
    price = _dec(value)
    return price if price is not None and 0 < price < ONE else None


def _side(win_probability: Decimal, price: Decimal | None, fee: FeeInfo, size: Decimal | None) -> dict | None:
    if price is None:
        return None
    cost = fee_per_contract(price, fee)
    return {"price": price, "size": size, "fee": cost, "net_edge": win_probability - price - cost}


def compare_outcome(outcome: dict, market: dict | None, fee: FeeInfo, evidence: str, supported_claims: int, s: Settings) -> dict:
    ticker = outcome["market_ticker"]
    if market is None:
        return {"market_ticker": ticker, "side": None, "meaningful": False, "reasons": ["Kalshi returned no market for this outcome"]}
    p, lo, hi = Decimal(str(outcome["probability"])), Decimal(str(outcome["min"])), Decimal(str(outcome["max"]))
    yes_bid = _dec(market.get("yes_bid_dollars"))
    yes_ask = _price(market.get("yes_ask_dollars"))
    # The NO ask is 1 minus the YES bid by definition; Kalshi also sends it, and its own field is used when present.
    no_ask = _price(market.get("no_ask_dollars")) if market.get("no_ask_dollars") is not None else (
        _price(ONE - yes_bid) if yes_bid is not None else None)
    yes = _side(p, yes_ask, fee, _dec(market.get("yes_ask_size_fp")))
    no = _side(ONE - p, no_ask, fee, _dec(market.get("yes_bid_size_fp")))  # contracts at the best YES bid are those at the NO ask

    candidates = {name: side for name, side in (("yes", yes), ("no", no)) if side}
    result = {
        "market_ticker": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask, "no_ask": no_ask,
        "yes": yes, "no": no, "side": None, "net_edge": None, "worst_case_edge": None, "meaningful": False, "reasons": [],
    }
    if not candidates:
        result["reasons"].append("no executable price (no ask on either side)")
        return result
    side = max(candidates, key=lambda n: candidates[n]["net_edge"])
    chosen = candidates[side]
    worst_probability = lo if side == "yes" else ONE - hi  # the forecaster least in favour of this side
    worst = worst_probability - chosen["price"] - chosen["fee"]
    result.update(side=side, net_edge=chosen["net_edge"], worst_case_edge=worst)

    reasons = result["reasons"]
    if chosen["net_edge"] < Decimal(str(s.edge_min)):
        reasons.append(f"net edge {chosen['net_edge']:.3f} is below EDGE_MIN {s.edge_min}")
    if worst <= 0:
        reasons.append("the least favourable forecaster shows no edge on this side")
    if evidence == "none" or supported_claims == 0:
        reasons.append("no supported evidence")
    elif supported_claims < s.min_supported_claims:
        reasons.append(f"only {supported_claims} supported claims (MIN_SUPPORTED_CLAIMS is {s.min_supported_claims})")
    size = chosen["size"]
    if size is None or size < Decimal(str(s.min_ask_size)):
        reasons.append(f"only {size if size is not None else 'an unknown number of'} contracts at the best price (MIN_ASK_SIZE is {s.min_ask_size})")
    result["meaningful"] = not reasons
    return result


def _plain(value):
    """Decimals to floats for JSON."""
    if isinstance(value, Decimal):
        return float(round(value, 6))
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def compare(prediction: dict, event_data: dict, fee: FeeInfo, s: Settings, priced_at: datetime) -> dict:
    markets = {m["ticker"]: m for m in (event_data.get("markets") or event_data.get("event", {}).get("markets") or [])}
    outcomes = [
        compare_outcome(o, markets.get(o["market_ticker"]), fee, prediction["evidence"], prediction["supported_claims"], s)
        for o in prediction["outcomes"]
    ]
    return _plain({
        "priced_at": priced_at.isoformat(),
        "fee": {"fee_type": fee.fee_type, "multiplier": fee.multiplier, "source": fee.source},
        "thresholds": {"edge_min": s.edge_min, "min_supported_claims": s.min_supported_claims, "min_ask_size": s.min_ask_size},
        "outcomes": outcomes,
    })


async def compare_run(client: KalshiClient, event_ticker: str, prediction: dict, s: Settings) -> dict:
    """Reads fresh prices and the series fee, then compares. Never raises for a Kalshi problem: it returns why not."""
    if "unavailable" in prediction:
        return {"unavailable": "There is no prediction to compare."}
    try:
        event_data = await asyncio.to_thread(client.get_event, event_ticker)
    except KalshiError as exc:
        log.warning("Prices for %s could not be read: %s", event_ticker, exc)
        return {"unavailable": f"Kalshi prices could not be read: {exc}"}
    priced_at = datetime.now(UTC)
    series_ticker = (event_data.get("event") or {}).get("series_ticker")
    fee = ASSUMED_FEE
    if series_ticker:
        try:
            fee = fee_info_from_series((await asyncio.to_thread(client.get_series, series_ticker)).get("series") or {})
        except KalshiError as exc:
            fee = FeeInfo(ASSUMED_FEE.fee_type, ASSUMED_FEE.multiplier, "assumed: the series could not be read")
            log.warning("Fee for series %s could not be read (%s); assuming quadratic, multiplier 1", series_ticker, exc)
    else:
        fee = FeeInfo(ASSUMED_FEE.fee_type, ASSUMED_FEE.multiplier, "assumed: the event has no series ticker")
        log.warning("Event %s has no series ticker; assuming quadratic fee, multiplier 1", event_ticker)
    if fee.source != "series":
        log.warning("Fee for %s is assumed: %s", event_ticker, fee.source)
    return compare(prediction, event_data, fee, s, priced_at)
