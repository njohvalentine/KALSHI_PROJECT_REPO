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
