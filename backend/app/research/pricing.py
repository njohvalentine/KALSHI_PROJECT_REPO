"""What a model call costs. Prices are OpenAI's standard tier, USD per million tokens, read from
OpenAI's pricing page on 2026-10-09. A model that is not listed has an unknown cost: we say so
instead of reporting zero."""

from dataclasses import dataclass
from decimal import Decimal

from app.research.schemas import Usage


@dataclass(frozen=True)
class Price:
    input: Decimal
    cached_input: Decimal
    output: Decimal


PRICES: dict[str, Price] = {
    "gpt-5.5": Price(Decimal("5.00"), Decimal("0.50"), Decimal("30.00")),
    "gpt-5.4": Price(Decimal("2.50"), Decimal("0.25"), Decimal("15.00")),
    "gpt-5.4-mini": Price(Decimal("0.75"), Decimal("0.075"), Decimal("4.50")),
    "gpt-5.4-nano": Price(Decimal("0.20"), Decimal("0.02"), Decimal("1.25")),
}
SEARCH_USD_PER_CALL = Decimal("10.00") / 1000
_PER_MILLION = Decimal(1_000_000)


def cost_usd(usage: Usage) -> Decimal | None:
    """Cost of one call, or None when the model is not in the price table."""
    price = PRICES.get(usage.model)
    if price is None:
        return None
    fresh_input = max(usage.input_tokens - usage.cached_tokens, 0)
    total = (
        Decimal(fresh_input) * price.input
        + Decimal(usage.cached_tokens) * price.cached_input
        + Decimal(usage.output_tokens) * price.output
    ) / _PER_MILLION + Decimal(usage.search_calls) * SEARCH_USD_PER_CALL
    return total.quantize(Decimal("0.000001"))


def total_cost(usages: list[Usage]) -> tuple[Decimal | None, str | None]:
    """Total over several calls. If any model is unpriced the total is unknown, with a note."""
    unknown = sorted({u.model for u in usages if u.model not in PRICES})
    if unknown:
        return None, "No price known for: " + ", ".join(unknown)
    return sum((cost_usd(u) for u in usages), Decimal("0")), None
