"""Database tables. Migrations are generated from these with Alembic."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="users_email_lowercase"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Only a keyed hash of the session token is stored, never the token itself.
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Forecast(Base):
    """One forecaster's probability for one outcome of a game. Forecasters never see the market price."""

    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 1", name="forecasts_probability_range"),
        Index("ix_forecasts_run_market", "run_id", "market_ticker"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64))
    market_ticker: Mapped[str] = mapped_column(String(128))  # one outcome (market) of the game
    forecaster_index: Mapped[int] = mapped_column(Integer)  # 0-based
    variant: Mapped[str] = mapped_column(String(64))  # the framing this forecaster was given
    probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    reasoning: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourcePage(Base):
    """A page cited by a run, saved with its retrieval time (the frozen record for backtests)."""

    __tablename__ = "source_pages"
    __table_args__ = (
        CheckConstraint(
            "fetch_status IN ('not_fetched', 'ok', 'blocked', 'empty_js', 'unsupported', 'too_large', 'failed')",
            name="source_pages_fetch_status_values",
        ),
        CheckConstraint("fetch_method IS NULL OR fetch_method IN ('plain', 'jina')", name="source_pages_fetch_method_values"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)  # the claims this link was cited for, NOT the page text
    # Our own fetch of the page (Milestone 3). Every outcome is recorded, none is skipped silently.
    fetch_status: Mapped[str] = mapped_column(String(16), default="not_fetched", server_default="not_fetched")
    fetch_method: Mapped[str | None] = mapped_column(String(8))  # plain or jina
    final_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_detail: Mapped[str | None] = mapped_column(Text)  # short reason shown to the user
    page_text: Mapped[str | None] = mapped_column(Text)
    page_text_hash: Mapped[str | None] = mapped_column(String(64))


class ClaimCheck(Base):
    """Whether one page supports one claim. A claim cited to several pages has one row per page."""

    __tablename__ = "claim_checks"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('supported', 'not_supported', 'could_not_check')", name="claim_checks_verdict_values"
        ),
        UniqueConstraint("run_id", "finding_index", "claim_index", "source_url", name="uq_claim_checks_claim_page"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    finding_index: Mapped[int] = mapped_column(Integer)  # position in runs.result["findings"]
    claim_index: Mapped[int] = mapped_column(Integer)  # position in that finding's claims
    source_url: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutcomeRecord(Base):
    """The frozen record of one forecast for one outcome of a game, made before the game, with the market
    price at that moment. Only the three result fields are ever changed, once the game has ended."""

    __tablename__ = "outcome_records"
    __table_args__ = (
        UniqueConstraint("run_id", "market_ticker", name="uq_outcome_records_run_market"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="outcome_records_probability_range"),
        CheckConstraint("baseline_probability IS NULL OR (baseline_probability >= 0 AND baseline_probability <= 1)",
                        name="outcome_records_baseline_range"),
        CheckConstraint("side IS NULL OR side IN ('yes', 'no')", name="outcome_records_side_values"),
        Index("ix_outcome_records_run", "run_id"),
        Index("ix_outcome_records_open", "resolved_at", "game_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64))
    event_ticker: Mapped[str] = mapped_column(String(128))
    market_ticker: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(Text)
    market_kind: Mapped[str] = mapped_column(String(10), default="winner", server_default="winner")  # winner, total, btts, spread
    sport: Mapped[str | None] = mapped_column(String(40))  # Kalshi's sport tag of the game's series, set when the record is made
    league: Mapped[str | None] = mapped_column(String(80))
    game_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    before_start: Mapped[bool | None] = mapped_column(Boolean)  # null when the start time is unknown
    # Our forecast
    probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    prob_min: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    prob_max: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    forecasters_valid: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(String(10))
    supported_claims: Mapped[int] = mapped_column(Integer)
    baseline_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # one call, no research
    # The market at that moment
    yes_bid: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    yes_ask: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    no_ask: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    yes_ask_size: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    yes_bid_size: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    priced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_type: Mapped[str | None] = mapped_column(String(32))
    fee_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    fee_source: Mapped[str | None] = mapped_column(String(64))
    # Bookmaker benchmark at that moment (winner markets only): consensus with the margin removed, Pinnacle alone, how many books
    book_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    book_pinnacle: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    book_count: Mapped[int | None] = mapped_column(Integer)
    book_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    book_note: Mapped[str | None] = mapped_column(Text)  # why there is no bookmaker price
    # What our rule said then
    side: Mapped[str | None] = mapped_column(String(3))
    net_edge: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    worst_case_edge: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    meaningful: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reasons: Mapped[list | None] = mapped_column(JSONB)
    # The result, filled in once the game has ended
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_yes: Mapped[bool | None] = mapped_column(Boolean)  # null when settled at another value (voided)
    settlement_value: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))


class Screening(Base):
    """One winner outcome checked against the bookmakers before any research (the free check on the Games page). Saved so the rule can
    be tested on real games later: the result fields are filled in once the game has ended."""

    __tablename__ = "screenings"
    __table_args__ = (
        Index("ix_screenings_event", "event_ticker", "created_at"),
        Index("ix_screenings_open", "resolved_at", "game_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_ticker: Mapped[str] = mapped_column(String(128))
    market_ticker: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    sport: Mapped[str | None] = mapped_column(String(40))
    league: Mapped[str | None] = mapped_column(String(80))
    game_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Kalshi at that moment
    yes_bid: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    yes_ask: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    no_ask: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    yes_ask_size: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    yes_bid_size: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # the bookmakers at that moment (margin removed) and what the rule said
    book_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    book_count: Mapped[int] = mapped_column(Integer)
    book_pinnacle: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    side: Mapped[str | None] = mapped_column(String(3))
    net_edge: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    enough_contracts: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    passes: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # the result, filled in once the game has ended
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_yes: Mapped[bool | None] = mapped_column(Boolean)


class Order(Base):
    """A simulated order: proposed, approved by a person, then placed in the simulation. Nothing is ever sent to Kalshi."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "state IN ('proposed', 'approved', 'rejected', 'expired', 'placed', 'simulated_rejected', 'settled')", name="orders_state_values"
        ),
        CheckConstraint("side IN ('yes', 'no')", name="orders_side_values"),
        CheckConstraint("contracts > 0", name="orders_contracts_positive"),
        CheckConstraint("price > 0 AND price < 1", name="orders_price_range"),
        Index("ix_orders_state_created", "state", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    run_id: Mapped[str] = mapped_column(String(64))
    event_ticker: Mapped[str] = mapped_column(String(128))
    market_ticker: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    game_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    side: Mapped[str] = mapped_column(String(3))
    price: Mapped[Decimal] = mapped_column(Numeric(7, 4))  # dollars per contract: the executable ask when it was prepared
    contracts: Mapped[int] = mapped_column(Integer)
    max_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))  # price times contracts plus the estimated fee
    fee_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    our_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))  # for the side we would buy
    gap: Mapped[Decimal] = mapped_column(Numeric(8, 4))  # net gap per contract after fees when prepared
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)  # why it was rejected, or why the simulation rejected it
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fill_contracts: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    fill_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    won: Mapped[bool | None] = mapped_column(Boolean)
    paper_result: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))  # dollars, for the contracts filled


class OrderLeg(Base):
    """One market of a ticket. A ticket pays only if every leg wins; a ticket with one leg is a plain order."""

    __tablename__ = "order_legs"
    __table_args__ = (
        CheckConstraint("side IN ('yes', 'no')", name="order_legs_side_values"),
        CheckConstraint("price > 0 AND price < 1", name="order_legs_price_range"),
        # One open ticket per market: kept in step with the ticket's state (open while it is proposed or approved).
        Index("uq_order_legs_one_open_per_market", "market_ticker", unique=True, postgresql_where=text("open")),
        Index("ix_order_legs_order", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str] = mapped_column(String(64))
    event_ticker: Mapped[str] = mapped_column(String(128))
    market_ticker: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    game_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    side: Mapped[str] = mapped_column(String(3))
    price: Mapped[Decimal] = mapped_column(Numeric(7, 4))  # the executable ask of this leg when the ticket was prepared
    our_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))  # for the side bought
    forecast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    won: Mapped[bool | None] = mapped_column(Boolean)


class OrderEvent(Base):
    """Append-only history of an order: every state change, who made it and why."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20))
    actor: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    detail: Mapped[str | None] = mapped_column(Text)


class Alert(Base):
    """Something worth telling the user, recorded in the app whether or not a chat channel exists."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("status IN ('recorded', 'sent', 'failed', 'held_back')", name="alerts_status_values"),
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_kind_event", "kind", "event_ticker"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(24))  # run_flagged, market_moved, no_longer_flagged, start_soon
    event_ticker: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str | None] = mapped_column(Text)  # why it was held back, or the kind of error that stopped sending


class Run(Base):
    """One research run for one game (a Kalshi event). The result is kept here so it survives restarts."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="runs_status_values"),
        CheckConstraint(
            "stage IS NULL OR stage IN ('research', 'fetch', 'check', 'forecast', 'compare', 'done')",
            name="runs_stage_values",
        ),
        Index("ix_runs_event_created", "event_ticker", "created_at"),
        Index("ix_runs_status", "status"),
        # At most one active run per game, enforced by the database so two simultaneous clicks
        # cannot both start (and pay for) a run.
        Index(
            "uq_runs_one_active_per_event",
            "event_ticker",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_ticker: Mapped[str] = mapped_column(String(128))
    event_title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    trigger: Mapped[str] = mapped_column(String(8), default="manual", server_default="manual")  # manual, or auto (the batch rule)
    refresh_of: Mapped[str | None] = mapped_column(String(64))  # set when this run is an update (lineups and late news) of that earlier run of the same game
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    # Where a running run is: research, fetch, check, forecast, compare or done. Null before it starts.
    stage: Mapped[str | None] = mapped_column(String(10))
    # Per outcome: median, spread, counts of supported claims and the market comparison.
    prediction: Mapped[dict | None] = mapped_column(JSONB)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    search_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))  # null when a model has no known price
    cost_note: Mapped[str | None] = mapped_column(Text)
    over_budget: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
