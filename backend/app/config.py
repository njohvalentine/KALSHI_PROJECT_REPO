"""Settings read from environment variables and validated at startup.

Required settings have no defaults: a missing or invalid one stops the process
with a message that names every problem (CLAUDE.md Module 4). Tuning knobs keep
safe defaults.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

log = logging.getLogger("app.config")

REQUIRED = ("DATABASE_URL", "KALSHI_API_BASE", "SESSION_SECRET")


class SettingsError(Exception):
    """One or more settings are missing or invalid."""


@dataclass(frozen=True)
class SeriesEntry:
    sport: str
    ticker: str
    league: str


# Single-game and match-winner series on Kalshi, each checked live on 2026-10-12 to have open games.
# Format of the setting: Sport:SERIES_TICKER:League label (the label is optional).
DEFAULT_SPORTS_SERIES = ",".join([
    "Soccer:KXEPLGAME:Premier League", "Soccer:KXUCLGAME:Champions League", "Soccer:KXUELGAME:Europa League",
    "Soccer:KXMLSGAME:MLS", "Soccer:KXLALIGAGAME:La Liga", "Soccer:KXSERIEAGAME:Serie A",
    "Soccer:KXBUNDESLIGAGAME:Bundesliga", "Soccer:KXLIGUE1GAME:Ligue 1",
    "Baseball:KXMLBGAME:MLB", "Baseball:KXNPBGAME:NPB (Japan)", "Baseball:KXKBOGAME:KBO (Korea)",
    "Tennis:KXATPMATCH:ATP", "Tennis:KXWTAMATCH:WTA",
    "Tennis:KXATPCHALLENGERMATCH:ATP Challenger", "Tennis:KXWTACHALLENGERMATCH:WTA Challenger",
])


def parse_sports_series(raw: str, problems: list[str]) -> tuple[SeriesEntry, ...]:
    entries: list[SeriesEntry] = []
    seen: set[str] = set()
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        parts = item.split(":", 2)
        sport, ticker = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
        league = parts[2].strip() if len(parts) > 2 and parts[2].strip() else ticker
        if not sport or not re.fullmatch(r"[A-Z0-9]+", ticker):
            problems.append(f"SPORTS_SERIES entry {item!r} must look like Sport:SERIES_TICKER:League label")
        elif ticker in seen:
            problems.append(f"SPORTS_SERIES lists {ticker} twice")
        else:
            seen.add(ticker)
            entries.append(SeriesEntry(sport, ticker, league))
    if not entries and not any("SPORTS_SERIES" in p for p in problems):
        problems.append("SPORTS_SERIES must list at least one series")
    return tuple(entries)


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
    sports_series: tuple[SeriesEntry, ...]
    games_cache_seconds: int
    sports_fetch_concurrency: int

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

    raw_series = env.get("SPORTS_SERIES", "").strip() or None  # empty counts as not set (Docker passes empty values)
    sports_series = parse_sports_series(raw_series if raw_series is not None else DEFAULT_SPORTS_SERIES, problems)
    cache_seconds = _parse_positive_int("GAMES_CACHE_SECONDS", env.get("GAMES_CACHE_SECONDS", "60"), problems)
    fetch_concurrency = _parse_positive_int(
        "SPORTS_FETCH_CONCURRENCY", env.get("SPORTS_FETCH_CONCURRENCY", "6"), problems
    )

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

    log.info(
        "Games list: %d series configured (%s).", len(sports_series),
        "from SPORTS_SERIES" if raw_series is not None else "default list; set SPORTS_SERIES to change it",
    )

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
        sports_series=sports_series,
        games_cache_seconds=cache_seconds,
        sports_fetch_concurrency=fetch_concurrency,
    )
