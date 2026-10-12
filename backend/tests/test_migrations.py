import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ, reason="needs a Postgres, see TEST_DATABASE_URL"
)

TABLES = {"users", "sessions", "forecasts", "source_pages"}
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fresh_db(monkeypatch):
    """A throwaway empty database, so tests never touch real data."""
    admin_url = make_url(os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1))
    name = f"migtest_{uuid.uuid4().hex[:10]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False).replace("+psycopg", "", 1))
    engine = create_engine(url)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


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
