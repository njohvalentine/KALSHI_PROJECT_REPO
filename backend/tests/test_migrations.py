import pytest
from alembic import command
from sqlalchemy import inspect, text

from tests.conftest import alembic_config as _config
from tests.conftest import needs_db

pytestmark = needs_db

TABLES = {"users", "sessions", "forecasts", "source_pages"}


def test_upgrade_creates_tables_and_downgrade_removes_them(fresh_db):
    command.upgrade(_config(), "head")
    assert TABLES <= set(inspect(fresh_db).get_table_names())

    command.downgrade(_config(), "base")
    assert not (TABLES & set(inspect(fresh_db).get_table_names()))


def test_ids_are_generated_and_constraints_enforced(fresh_db):
    command.upgrade(_config(), "head")
    with fresh_db.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (email, password_hash) VALUES ('a@b.c', 'h') RETURNING id")
        ).scalar_one()
        assert uid >= 1
    with pytest.raises(Exception, match="users_email_lowercase"):
        with fresh_db.begin() as conn:
            conn.execute(text("INSERT INTO users (email, password_hash) VALUES ('A@B.C', 'h')"))
    with pytest.raises(Exception, match="forecasts_probability_range"):
        with fresh_db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO forecasts (run_id, market_ticker, probability, kalshi_price)"
                    " VALUES ('r', 'T', 1.5, 0.5)"
                )
            )
    with fresh_db.begin() as conn:  # several forecasts per market are allowed (history)
        for p in (0.4, 0.6):
            conn.execute(
                text(
                    "INSERT INTO forecasts (run_id, market_ticker, probability, kalshi_price)"
                    f" VALUES ('r', 'T', {p}, 0.5)"
                )
            )
        assert conn.execute(text("SELECT count(*) FROM forecasts WHERE market_ticker='T'")).scalar_one() == 2


def test_migrations_refuse_to_run_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        command.upgrade(_config(), "head")
