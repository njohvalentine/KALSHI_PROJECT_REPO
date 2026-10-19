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


def test_research_defaults_and_off_without_key(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.config")
    s = load_settings(GOOD)
    assert s.research_enabled is False and s.openai_api_key is None
    assert (s.planner_model, s.researcher_model) == ("gpt-5.4-mini", "gpt-5.4")
    assert (s.max_researchers, s.max_searches_per_researcher, s.researcher_max_output_tokens) == (3, 3, 4000)
    assert (s.max_concurrent_runs, s.run_cost_warn_usd, s.research_reasoning_effort) == (2, 3.0, "low")
    assert "Research is OFF" in caplog.text  # the off state is visible, not silent


def test_research_on_with_key_and_key_never_logged(caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="app.config")
    s = load_settings({**GOOD, "OPENAI_API_KEY": "sk-secret-value"})
    assert s.research_enabled
    assert "Research is ON" in caplog.text and "sk-secret-value" not in caplog.text


@pytest.mark.parametrize("name,value", [
    ("RESEARCH_REASONING_EFFORT", "none"),
    ("RESEARCH_REASONING_EFFORT", "extreme"),
    ("MAX_RESEARCHERS", "0"),
    ("MAX_SEARCHES_PER_RESEARCHER", "x"),
    ("RESEARCHER_MAX_OUTPUT_TOKENS", "-5"),
    ("MAX_CONCURRENT_RUNS", "0"),
    ("RUN_COST_WARN_USD", "0"),
    ("PLANNER_MODEL", " "),
])
def test_bad_research_settings_rejected(name, value):
    with pytest.raises(SettingsError, match=name.split("_")[0] if name != "PLANNER_MODEL" else "MODEL"):
        load_settings({**GOOD, name: value})


def test_the_watcher_line_says_where_alerts_go_and_never_that_no_chat_channel_exists(caplog):
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
    import logging

    base = {**GOOD, "MONITOR_ENABLED": "true"}
    with caplog.at_level(logging.INFO, logger="app.config"):
        load_settings({**base, "ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": "123456"})
    on = next(m for m in caplog.messages if m.startswith("The watcher is ON"))
    assert "sent to Telegram and recorded in the app" in on
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.config"):
        load_settings(base)
    off = next(m for m in caplog.messages if m.startswith("The watcher is ON"))
    assert "only recorded in the app" in off
    assert "no chat channel" not in on + off
