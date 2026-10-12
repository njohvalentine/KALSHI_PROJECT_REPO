import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DbSession

from app.cli import create_user
from app.config import load_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
needs_db = pytest.mark.skipif(
    "TEST_DATABASE_URL" not in os.environ, reason="needs a Postgres, see TEST_DATABASE_URL"
)


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def fresh_db(monkeypatch):
    """A throwaway empty database, so tests never touch real data."""
    admin_url = make_url(os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1))
    name = f"test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name)
    plain_url = url.render_as_string(hide_password=False).replace("+psycopg", "", 1)
    monkeypatch.setenv("DATABASE_URL", plain_url)
    engine = create_engine(url)
    engine.plain_url = plain_url
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


EMAIL = "owner@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
def make_client(fresh_db):
    """Builds an app on a migrated empty database with one user. Settings can be overridden."""
    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        create_user(db, EMAIL, PASSWORD)

    def build(**overrides):
        env = {
            "DATABASE_URL": fresh_db.plain_url,
            "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
            "SESSION_SECRET": "s" * 40,
            "SESSION_COOKIE_SECURE": "false",
            "LOGIN_MAX_ATTEMPTS": "3",
            **overrides,
        }
        return TestClient(create_app(load_settings(env)))

    build.engine = fresh_db
    return build
