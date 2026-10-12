import pytest

from app.config import SettingsError, load_settings

GOOD = {
    "DATABASE_URL": "postgresql://u:p@db:5432/app",
    "KALSHI_API_BASE": "https://external-api.kalshi.com/trade-api/v2/",
    "SESSION_SECRET": "x" * 32,
}


def test_valid_settings_and_defaults():
    s = load_settings(GOOD)
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@db:5432/app"
    assert s.kalshi_api_base == "https://external-api.kalshi.com/trade-api/v2"
    assert s.langsmith_tracing is False
    assert (s.session_ttl_hours, s.login_max_attempts, s.login_lockout_minutes) == (12, 5, 15)
    assert s.session_cookie_secure is True


@pytest.mark.parametrize("missing", ["DATABASE_URL", "KALSHI_API_BASE", "SESSION_SECRET"])
def test_missing_required_setting_is_named(missing):
    env = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(SettingsError, match=missing):
        load_settings(env)


def test_all_problems_reported_together():
    with pytest.raises(SettingsError) as err:
        load_settings({})
    for name in ("DATABASE_URL", "KALSHI_API_BASE", "SESSION_SECRET"):
        assert name in str(err.value)


def test_short_secret_and_bad_url_rejected():
    with pytest.raises(SettingsError, match="SESSION_SECRET must be at least 32"):
        load_settings({**GOOD, "SESSION_SECRET": "short"})
    with pytest.raises(SettingsError, match="DATABASE_URL must start with postgresql://"):
        load_settings({**GOOD, "DATABASE_URL": "sqlite:///x.db"})


def test_tracing_requires_langsmith_key():
    with pytest.raises(SettingsError, match="LANGSMITH_API_KEY is required"):
        load_settings({**GOOD, "LANGSMITH_TRACING": "true"})
    s = load_settings({**GOOD, "LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "k"})
    assert s.langsmith_tracing and s.langsmith_api_key == "k"


def test_bad_bool_and_int_rejected():
    with pytest.raises(SettingsError, match="LANGSMITH_TRACING must be"):
        load_settings({**GOOD, "LANGSMITH_TRACING": "yes"})
    with pytest.raises(SettingsError, match="SESSION_TTL_HOURS"):
        load_settings({**GOOD, "SESSION_TTL_HOURS": "0"})
