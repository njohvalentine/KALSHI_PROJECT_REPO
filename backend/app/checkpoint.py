"""LangGraph saved progress (checkpoints) in Postgres, so paused or interrupted runs survive restarts."""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


# Arbitrary fixed number: only one process at a time may create or upgrade the checkpoint tables.
SETUP_LOCK_KEY = 7_203_141_001


class CheckpointerError(Exception):
    pass


async def open_checkpointer(
    database_url: str, *, connect_timeout: float = 10.0, lock_timeout: float = 60.0
) -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:
    """Opens a connection pool and creates LangGraph's checkpoint tables if they are missing.

    The connection settings are the ones LangGraph's own AsyncPostgresSaver.from_conn_string uses
    (checked in the installed package): autocommit on, no prepared statements, rows as dicts.
    Raises CheckpointerError if the database cannot be reached, so the app does not start half-working.
    """
    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    try:
        await pool.open(wait=True, timeout=connect_timeout)
        saver = AsyncPostgresSaver(pool)
        # Table setup must not run in several processes at once. Waiters poll with try-lock instead
        # of blocking inside a statement: LangGraph's setup uses CREATE INDEX CONCURRENTLY, which
        # waits for every other running statement, so a blocked waiter would deadlock it.
        async with pool.connection() as lock_conn:
            loop = asyncio.get_running_loop()
            give_up_at = loop.time() + lock_timeout
            while True:
                cursor = await lock_conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (SETUP_LOCK_KEY,))
                if (await cursor.fetchone())["got"]:
                    break
                if loop.time() > give_up_at:
                    raise TimeoutError("another process is holding the checkpoint setup lock")
                await asyncio.sleep(0.2)
            try:
                await saver.setup()
            finally:
                await lock_conn.execute("SELECT pg_advisory_unlock(%s)", (SETUP_LOCK_KEY,))
    except Exception as exc:
        await pool.close()
        raise CheckpointerError(
            f"Cannot set up saved progress in the database (check DATABASE_URL): {type(exc).__name__}: {exc}"
        ) from exc
    return pool, saver
