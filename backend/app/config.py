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
    openai_api_key: str | None
    planner_model: str
    researcher_model: str
    research_reasoning_effort: str
    max_researchers: int
    max_searches_per_researcher: int
    researcher_max_output_tokens: int
    max_concurrent_runs: int
    run_cost_warn_usd: float

    @property
    def research_enabled(self) -> bool:
        return self.openai_api_key is not None

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


def _parse_positive_float(name: str, raw: str, problems: list[str]) -> float:
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    problems.append(f"{name} must be a positive number, got {raw!r}")
    return 1.0


EFFORTS = ("low", "medium", "high")  # never "none": OpenAI warns it can lower web search quality


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

    openai_api_key = env.get("OPENAI_API_KEY", "").strip() or None
    planner_model = env.get("PLANNER_MODEL", "gpt-5.4-mini").strip()
    researcher_model = env.get("RESEARCHER_MODEL", "gpt-5.4").strip()
    if not planner_model or not researcher_model:
        problems.append("PLANNER_MODEL and RESEARCHER_MODEL must not be empty")
    effort = env.get("RESEARCH_REASONING_EFFORT", "low").strip()
    if effort not in EFFORTS:
        problems.append(f"RESEARCH_REASONING_EFFORT must be one of {', '.join(EFFORTS)}, got {effort!r}")
    max_researchers = _parse_positive_int("MAX_RESEARCHERS", env.get("MAX_RESEARCHERS", "4"), problems)
    max_searches = _parse_positive_int(
        "MAX_SEARCHES_PER_RESEARCHER", env.get("MAX_SEARCHES_PER_RESEARCHER", "3"), problems
    )
    max_output = _parse_positive_int(
        "RESEARCHER_MAX_OUTPUT_TOKENS", env.get("RESEARCHER_MAX_OUTPUT_TOKENS", "4000"), problems
    )
    max_runs = _parse_positive_int("MAX_CONCURRENT_RUNS", env.get("MAX_CONCURRENT_RUNS", "2"), problems)
    warn_usd = _parse_positive_float("RUN_COST_WARN_USD", env.get("RUN_COST_WARN_USD", "3.00"), problems)

    if problems:
        raise SettingsError("Invalid settings:\n- " + "\n- ".join(problems))

    if not cookie_secure:
        log.warning("SESSION_COOKIE_SECURE=false: session cookies are sent over plain http. Local use only.")
    # LangSmith reads LANGSMITH_TRACING and LANGSMITH_API_KEY from the environment itself.
    log.info("LangSmith tracing is %s.", "ON" if tracing else "off (LANGSMITH_TRACING is not 'true')")

    if openai_api_key:
        log.info("Research is ON: planner model %s, researcher model %s.", planner_model, researcher_model)
    else:
        log.warning("Research is OFF: OPENAI_API_KEY is not set. Starting a run will be refused.")

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
        openai_api_key=openai_api_key,
        planner_model=planner_model,
        researcher_model=researcher_model,
        research_reasoning_effort=effort,
        max_researchers=max_researchers,
        max_searches_per_researcher=max_searches,
        researcher_max_output_tokens=max_output,
        max_concurrent_runs=max_runs,
        run_cost_warn_usd=warn_usd,
    )
