import os

import pytest
from fastapi.testclient import TestClient

from app.config import SettingsError, load_settings
from app.main import create_app

BASE = {
    "KALSHI_API_BASE": "https://external-api.kalshi.com/trade-api/v2",
    "SESSION_SECRET": "x" * 32,
}


def test_app_refuses_to_start_without_required_settings(monkeypatch):
    for name in ("DATABASE_URL", "KALSHI_API_BASE", "SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        with TestClient(create_app()):
            pass


@pytest.mark.skipif("TEST_DATABASE_URL" not in os.environ, reason="needs a Postgres, see TEST_DATABASE_URL")
def test_health_ok_with_db():
    settings = load_settings({**BASE, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]})
    with TestClient(create_app(settings)) as client:
        r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": True}


@pytest.mark.skipif("TEST_DATABASE_URL" not in os.environ, reason="needs a Postgres, see TEST_DATABASE_URL")
def test_health_reports_db_that_goes_away_after_startup():
    from sqlalchemy import create_engine

    settings = load_settings({**BASE, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]})
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        # Nothing listens on port 1, so connecting fails straight away.
        client.app.state.engine = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/x")
        r = client.get("/health")
    assert r.status_code == 503 and r.json() == {"status": "degraded", "db": False}
