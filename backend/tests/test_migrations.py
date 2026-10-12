import pytest
from alembic import command
from sqlalchemy import inspect, text

from tests.conftest import alembic_config as _config
from tests.conftest import needs_db

pytestmark = needs_db

TABLES = {"users", "sessions", "forecasts", "source_pages", "runs"}


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


def test_runs_table_rules(fresh_db):
    command.upgrade(_config(), "head")
    with fresh_db.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, market_ticker, market_title, status, plan) VALUES ('r1', 'T', 'Q', 'queued', '{\"angles\": [1]}')"))
        assert conn.execute(text("SELECT plan->'angles'->>0 FROM runs WHERE id='r1'")).scalar_one() == "1"
        assert conn.execute(text("SELECT input_tokens, over_budget, cost_usd FROM runs")).one() == (0, False, None)
    with pytest.raises(Exception, match="runs_status_values"):
        with fresh_db.begin() as conn:
            conn.execute(text("INSERT INTO runs (id, market_ticker, market_title, status) VALUES ('r2', 'T', 'Q', 'bogus')"))


def test_models_match_migrations_and_langgraph_tables_are_left_alone(fresh_db):
    # `alembic check` fails if the models and the migrations disagree. LangGraph's own tables exist
    # in the database too; without the filter in env.py, autogenerate wanted to drop them.
    import asyncio

    from app.checkpoint import open_checkpointer

    command.upgrade(_config(), "head")

    async def create_langgraph_tables():
        pool, _ = await open_checkpointer(fresh_db.plain_url, connect_timeout=10)
        await pool.close()

    asyncio.run(create_langgraph_tables())
    assert "checkpoints" in set(inspect(fresh_db).get_table_names())
    command.check(_config())  # raises if there is any difference
    command.downgrade(_config(), "base")
    assert "checkpoints" in set(inspect(fresh_db).get_table_names())  # downgrade leaves them alone too
