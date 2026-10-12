import pytest
from alembic import command
from sqlalchemy import inspect, text

from tests.conftest import alembic_config as _config
from tests.conftest import needs_db

pytestmark = needs_db

TABLES = {"users", "sessions", "forecasts", "source_pages", "runs", "claim_checks"}


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


def test_milestone_3_tables_and_rules(fresh_db):
    command.upgrade(_config(), "head")
    assert {"claim_checks", "forecasts"} <= set(inspect(fresh_db).get_table_names())
    forecast = "INSERT INTO forecasts (run_id, market_ticker, forecaster_index, variant, probability, reasoning, model)"
    with fresh_db.begin() as conn:  # several forecasters per outcome are the point
        for i, p in enumerate((0.4, 0.6)):
            conn.execute(text(f"{forecast} VALUES ('r', 'T', {i}, 'v', {p}, 'why', 'm')"))
        assert conn.execute(text("SELECT count(*) FROM forecasts WHERE market_ticker='T'")).scalar_one() == 2
    with pytest.raises(Exception, match="forecasts_probability_range"):
        with fresh_db.begin() as conn:
            conn.execute(text(f"{forecast} VALUES ('r', 'T', 2, 'v', 1.5, 'why', 'm')"))

    check = "INSERT INTO claim_checks (run_id, finding_index, claim_index, source_url, verdict, reason, model)"
    with fresh_db.begin() as conn:
        conn.execute(text(f"{check} VALUES ('r', 0, 0, 'http://a', 'supported', 'ok', 'm')"))
        conn.execute(text(f"{check} VALUES ('r', 0, 0, 'http://b', 'not_supported', 'no', 'm')"))  # other page: fine
    with pytest.raises(Exception, match="uq_claim_checks_claim_page"):
        with fresh_db.begin() as conn:
            conn.execute(text(f"{check} VALUES ('r', 0, 0, 'http://a', 'supported', 'again', 'm')"))
    with pytest.raises(Exception, match="claim_checks_verdict_values"):
        with fresh_db.begin() as conn:
            conn.execute(text(f"{check} VALUES ('r', 1, 0, 'http://a', 'maybe', 'x', 'm')"))

    page = "INSERT INTO source_pages (run_id, url, retrieved_at, content_hash, content{cols}) VALUES ('r', 'http://a', now(), 'h', 'c'{vals})"
    with fresh_db.begin() as conn:
        conn.execute(text(page.format(cols="", vals="")))
        assert conn.execute(text("SELECT fetch_status, page_text FROM source_pages")).one() == ("not_fetched", None)
    with pytest.raises(Exception, match="source_pages_fetch_status_values"):
        with fresh_db.begin() as conn:
            conn.execute(text(page.format(cols=", fetch_status", vals=", 'bogus'")))
    with pytest.raises(Exception, match="source_pages_fetch_method_values"):
        with fresh_db.begin() as conn:
            conn.execute(text(page.format(cols=", fetch_method", vals=", 'curl'")))
    with pytest.raises(Exception, match="runs_stage_values"):
        with fresh_db.begin() as conn:
            conn.execute(text("INSERT INTO runs (id, event_ticker, event_title, status, stage) VALUES ('s', 'T', 'Q', 'queued', 'bogus')"))


def test_replacing_forecasts_refuses_to_delete_data(fresh_db):
    command.upgrade(_config(), "ac06201bd470")
    with fresh_db.begin() as conn:
        conn.execute(text("INSERT INTO forecasts (run_id, market_ticker, probability, kalshi_price) VALUES ('r', 'T', 0.5, 0.5)"))
    with pytest.raises(Exception, match="will not delete data"):
        command.upgrade(_config(), "head")


def test_migrations_refuse_to_run_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        command.upgrade(_config(), "head")


def test_runs_table_rules(fresh_db):
    command.upgrade(_config(), "head")
    with fresh_db.begin() as conn:
        conn.execute(text("INSERT INTO runs (id, event_ticker, event_title, status, plan) VALUES ('r1', 'T', 'Q', 'queued', '{\"angles\": [1]}')"))
        assert conn.execute(text("SELECT plan->'angles'->>0 FROM runs WHERE id='r1'")).scalar_one() == "1"
        assert conn.execute(text("SELECT input_tokens, over_budget, cost_usd FROM runs")).one() == (0, False, None)
    with pytest.raises(Exception, match="runs_status_values"):
        with fresh_db.begin() as conn:
            conn.execute(text("INSERT INTO runs (id, event_ticker, event_title, status) VALUES ('r2', 'T', 'Q', 'bogus')"))


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
