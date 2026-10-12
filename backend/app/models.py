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
    """One row per forecast, so a market can have a history of updates (re-checks)."""

    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("probability >= 0 AND probability <= 1", name="forecasts_probability_range"),
        CheckConstraint("kalshi_price >= 0 AND kalshi_price <= 1", name="forecasts_price_range"),
        CheckConstraint("outcome IN ('yes', 'no')", name="forecasts_outcome_values"),
        Index("ix_forecasts_market_created", "market_ticker", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    market_ticker: Mapped[str] = mapped_column(String(128))
    probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    # Kalshi's price for yes at the moment of the forecast, as a fraction (0.48 = 48 cents).
    kalshi_price: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome: Mapped[str | None] = mapped_column(String(3))  # filled in when the market resolves


class SourcePage(Base):
    """A page cited by a run, saved with its retrieval time (the frozen record for backtests)."""

    __tablename__ = "source_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)


class Run(Base):
    """One research run for one game (a Kalshi event). The result is kept here so it survives restarts."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="runs_status_values"),
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
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    search_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))  # null when a model has no known price
    cost_note: Mapped[str | None] = mapped_column(Text)
    over_budget: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
