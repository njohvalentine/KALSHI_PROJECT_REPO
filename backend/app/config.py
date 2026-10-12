"""Settings read from environment variables and validated at startup.

Required settings have no defaults: a missing or invalid one stops the process
with a message that names every problem (CLAUDE.md Module 4). Tuning knobs keep
safe defaults.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

log = logging.getLogger("app.config")

REQUIRED = ("DATABASE_URL", "KALSHI_API_BASE", "SESSION_SECRET")


class SettingsError(Exception):
    """One or more settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    kalshi_api_base: str
    session_secret: str
    langsmith_tracing: bool
    langsmith_api_key: str | None
    session_ttl_hours: int
    login_max_attempts: int
    login_lockout_minutes: int
    session_cookie_secure: bool

    @property
    def sqlalchemy_url(self) -> str:
        # DATABASE_URL is a plain libpq URL (also used by LangGraph's checkpointer).
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def _parse_bool(name: str, raw: str, problems: list[str]) -> bool:
    if raw in ("true", "false"):
        return raw == "true"
    problems.append(f"{name} must be 'true' or 'false', got {raw!r}")
    return False


def _parse_positive_int(name: str, raw: str, problems: list[str]) -> int:
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    problems.append(f"{name} must be a positive whole number, got {raw!r}")
    return 1


def load_settings(env: Mapping[str, str]) -> Settings:
    problems: list[str] = []

    for name in REQUIRED:
        if not env.get(name, "").strip():
            problems.append(f"{name} is required and is not set")

    database_url = env.get("DATABASE_URL", "").strip()
    if database_url and not database_url.startswith("postgresql://"):
        problems.append("DATABASE_URL must start with postgresql://")

    kalshi_api_base = env.get("KALSHI_API_BASE", "").strip().rstrip("/")
    if kalshi_api_base and not kalshi_api_base.startswith(("https://", "http://")):
        problems.append("KALSHI_API_BASE must start with https:// or http://")

    session_secret = env.get("SESSION_SECRET", "").strip()
    if session_secret and len(session_secret) < 32:
        problems.append("SESSION_SECRET must be at least 32 characters")

    tracing = _parse_bool("LANGSMITH_TRACING", env.get("LANGSMITH_TRACING", "false"), problems)
    langsmith_api_key = env.get("LANGSMITH_API_KEY", "").strip() or None
    if tracing and not langsmith_api_key:
        problems.append("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true")

    cookie_secure = _parse_bool(
        "SESSION_COOKIE_SECURE", env.get("SESSION_COOKIE_SECURE", "true"), problems
    )
    ttl = _parse_positive_int("SESSION_TTL_HOURS", env.get("SESSION_TTL_HOURS", "12"), problems)
    attempts = _parse_positive_int(
        "LOGIN_MAX_ATTEMPTS", env.get("LOGIN_MAX_ATTEMPTS", "5"), problems
    )
    lockout = _parse_positive_int(
        "LOGIN_LOCKOUT_MINUTES", env.get("LOGIN_LOCKOUT_MINUTES", "15"), problems
    )

    if problems:
        raise SettingsError("Invalid settings:\n- " + "\n- ".join(problems))

    if not cookie_secure:
        log.warning("SESSION_COOKIE_SECURE=false: session cookies are sent over plain http. Local use only.")
    # LangSmith reads LANGSMITH_TRACING and LANGSMITH_API_KEY from the environment itself.
    log.info("LangSmith tracing is %s.", "ON" if tracing else "off (LANGSMITH_TRACING is not 'true')")

    return Settings(
        database_url=database_url,
        kalshi_api_base=kalshi_api_base,
        session_secret=session_secret,
        langsmith_tracing=tracing,
        langsmith_api_key=langsmith_api_key,
        session_ttl_hours=ttl,
        login_max_attempts=attempts,
        login_lockout_minutes=lockout,
        session_cookie_secure=cookie_secure,
    )
