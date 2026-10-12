"""runs are per event

Revision ID: ac06201bd470
Revises: d178265cbd60
Create Date: 2026-10-12 14:32:25.950972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac06201bd470'
down_revision: Union[str, Sequence[str], None] = 'd178265cbd60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A run is now about one game (an event), not one market: rename the columns and indexes."""
    op.alter_column("runs", "market_ticker", new_column_name="event_ticker")
    op.alter_column("runs", "market_title", new_column_name="event_title")
    op.execute("ALTER INDEX ix_runs_market_created RENAME TO ix_runs_event_created")
    op.execute("ALTER INDEX uq_runs_one_active_per_market RENAME TO uq_runs_one_active_per_event")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER INDEX uq_runs_one_active_per_event RENAME TO uq_runs_one_active_per_market")
    op.execute("ALTER INDEX ix_runs_event_created RENAME TO ix_runs_market_created")
    op.alter_column("runs", "event_title", new_column_name="market_title")
    op.alter_column("runs", "event_ticker", new_column_name="market_ticker")
