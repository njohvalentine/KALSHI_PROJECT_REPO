import asyncio

import pytest
from sqlalchemy import inspect

from app.checkpoint import CheckpointerError, open_checkpointer
from app.config import load_settings
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import needs_db

CHECKPOINT_TABLES = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}


@needs_db
def test_startup_creates_checkpoint_tables_and_is_repeatable(fresh_db):
    settings = load_settings({
        "DATABASE_URL": fresh_db.plain_url,
        "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
        "SESSION_SECRET": "s" * 40,
    })
    for _ in range(2):  # a second start must not fail on existing tables
        with TestClient(create_app(settings)):
            pass
    assert CHECKPOINT_TABLES <= set(inspect(fresh_db).get_table_names())


def test_bad_database_url_fails_at_startup_with_a_clear_message(monkeypatch):
    # Nothing listens on port 1.
    with pytest.raises(CheckpointerError, match="check DATABASE_URL"):
        asyncio.run(open_checkpointer("postgresql://u:p@127.0.0.1:1/x", connect_timeout=2))
    settings = load_settings({
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:1/x",
        "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
        "SESSION_SECRET": "s" * 40,
    })
    import functools

    import app.main

    monkeypatch.setattr(app.main, "open_checkpointer", functools.partial(open_checkpointer, connect_timeout=2))
    with pytest.raises(CheckpointerError):
        with TestClient(create_app(settings)):
            pass


@needs_db
def test_many_processes_starting_at_once_do_not_block_each_other(fresh_db):
    # LangGraph's setup uses CREATE INDEX CONCURRENTLY; a plain blocking lock around it deadlocked.
    async def start_many():
        async def one():
            pool, _ = await open_checkpointer(fresh_db.plain_url, connect_timeout=10, lock_timeout=30)
            await pool.close()

        await asyncio.wait_for(asyncio.gather(*[one() for _ in range(6)]), timeout=45)

    asyncio.run(start_many())
    assert CHECKPOINT_TABLES <= set(inspect(fresh_db).get_table_names())
