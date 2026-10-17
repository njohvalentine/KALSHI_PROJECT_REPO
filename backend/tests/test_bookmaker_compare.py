"""The bookmakers' view of a market, beside the Kalshi price: margin (already out of the input), fees and contracts on offer."""

from datetime import UTC, datetime
from decimal import Decimal

from app.config import load_settings
from app.research.compare import FeeInfo, compare_outcome
from tests.conftest import needs_db
from tests.test_pipeline import run_game, signed_in

ENV = {"DATABASE_URL": "postgresql://u:p@db:5432/x", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}
S = load_settings(ENV)
FEE = FeeInfo("quadratic", Decimal(1), "series")  # 0.07 x price x (1 - price)
OUTCOME = {"market_ticker": "KX-H", "probability": 0.55, "min": 0.50, "max": 0.60}


def market(ask_size="100"):
    return {"yes_bid_dollars": "0.49", "yes_ask_dollars": "0.50", "no_ask_dollars": "0.51", "yes_ask_size_fp": ask_size, "yes_bid_size_fp": "100"}


def gap(book_probability, ask_size="100", outcome=OUTCOME):
    result = compare_outcome(outcome, market(ask_size), FEE, "supported", 7, S, 0.50, {"probability": book_probability, "pinnacle": 0.6, "count": 19}, "2026-10-17T10:00:00+00:00")
    return result["book"]


def test_the_yes_side_is_worth_the_bookmaker_probability_minus_the_price_minus_the_fee():
    b = gap(0.60)
    fee = Decimal("0.07") * Decimal("0.5") * Decimal("0.5")  # 0.0175
    assert b["side"] == "yes" and b["edge"] == Decimal("0.60") - Decimal("0.50") - fee
    assert b["enough_contracts"] is True and b["passes"] is True  # 8.25 cents is at least EDGE_MIN (5 cents), 100 contracts at least 10
    assert b["count"] == 19 and b["pinnacle"] == 0.6 and b["read_at"] == "2026-10-17T10:00:00+00:00"
    assert b["agrees_with_us"] is True  # we also lean yes (0.55 against an ask of 0.50)


def test_the_no_side_uses_the_no_ask_and_can_disagree_with_us():
    b = gap(0.30)
    fee = Decimal("0.07") * Decimal("0.51") * Decimal("0.49")
    assert b["side"] == "no" and b["edge"] == Decimal("0.70") - Decimal("0.51") - fee
    assert b["passes"] is True and b["agrees_with_us"] is False  # the bookmakers favour "no", we favour "yes"


def test_too_few_contracts_at_the_price_do_not_pass():
    b = gap(0.60, ask_size="5")
    assert b["edge"] > Decimal("0.05") and b["enough_contracts"] is False and b["passes"] is False


def test_no_gap_when_the_bookmakers_and_the_price_agree():
    b = gap(0.50)  # both sides lose the fee
    assert b["edge"] <= 0 and b["passes"] is False and b["agrees_with_us"] is None


def test_a_market_without_a_bookmaker_price_has_no_book_entry():
    assert "book" not in compare_outcome(OUTCOME, market(), FEE, "supported", 7, S, 0.50)


@needs_db
def test_a_run_reads_the_bookmakers_before_the_comparison_and_the_record_keeps_the_same_read(make_client, monkeypatch):
    from app.research import pipeline

    order = []
    when = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)

    async def fake_book(*args, **kwargs):
        order.append("book")
        return {"at": when, "by_ticker": {"KX-1-H": {"probability": 0.60, "pinnacle": 0.61, "count": 19}, "KX-1-A": {"probability": 0.40, "pinnacle": 0.39, "count": 19}}, "note": None}

    real_compare = pipeline.compare_run

    async def spy_compare(*args, **kwargs):
        order.append("compare")
        assert kwargs["book"]["by_ticker"]["KX-1-H"]["probability"] == 0.60
        return await real_compare(*args, **kwargs)

    monkeypatch.setattr(pipeline, "book_for_game", fake_book)
    monkeypatch.setattr(pipeline, "compare_run", spy_compare)
    client = signed_in(make_client)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and order == ["book", "compare"]  # one read, before the comparison
    outcomes = {o["market_ticker"]: o for o in run["prediction"]["comparison"]["outcomes"]}
    assert outcomes["KX-1-H"]["book"]["probability"] == 0.60 and outcomes["KX-1-H"]["book"]["read_at"].startswith("2026-10-17T09:00")
    assert run["book_note"] is None  # the game has a bookmaker price


@needs_db
def test_a_failed_bookmaker_read_leaves_the_note_and_never_fails_the_run(make_client, monkeypatch):
    from app.research import pipeline

    async def no_price(*args, **kwargs):
        return {"at": None, "by_ticker": {}, "note": "no bookmaker source for this league (the odds feed has no active sport for it)"}

    monkeypatch.setattr(pipeline, "book_for_game", no_price)
    client = signed_in(make_client)
    try:
        run = run_game(client)
    finally:
        client.__exit__(None, None, None)
    assert run["status"] == "done" and all("book" not in o for o in run["prediction"]["comparison"]["outcomes"])
    assert run["book_note"] == "no bookmaker source for this league (the odds feed has no active sport for it)"
