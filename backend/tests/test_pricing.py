from decimal import Decimal

from app.research.pricing import cost_usd, total_cost
from app.research.schemas import Usage


def test_cost_with_hand_computed_numbers():
    # gpt-5.4: 2.50 in, 0.25 cached, 15.00 out per million. 2 searches at $0.01 each.
    u = Usage(model="gpt-5.4", input_tokens=100_000, cached_tokens=20_000, output_tokens=5_000, search_calls=2)
    # fresh input 80,000 -> 0.20 ; cached 20,000 -> 0.005 ; output 5,000 -> 0.075 ; searches 0.02
    assert cost_usd(u) == Decimal("0.300000")


def test_mini_model_and_no_tokens():
    assert cost_usd(Usage(model="gpt-5.4-mini", input_tokens=1_000_000, output_tokens=1_000_000)) == Decimal("5.250000")
    assert cost_usd(Usage(model="gpt-5.4")) == Decimal("0.000000")


def test_cached_tokens_never_make_input_negative():
    u = Usage(model="gpt-5.4", input_tokens=10, cached_tokens=50)
    assert cost_usd(u) is not None and cost_usd(u) >= 0


def test_unknown_model_has_unknown_cost_not_zero():
    u = Usage(model="gpt-future", input_tokens=1000, output_tokens=1000)
    assert cost_usd(u) is None
    total, note = total_cost([Usage(model="gpt-5.4", input_tokens=1000), u])
    assert total is None and "gpt-future" in note


def test_total_adds_up():
    calls = [Usage(model="gpt-5.4-mini", input_tokens=1_000_000), Usage(model="gpt-5.4", output_tokens=1_000_000, search_calls=100)]
    total, note = total_cost(calls)
    assert note is None and total == Decimal("0.75") + Decimal("15.00") + Decimal("1.00")
