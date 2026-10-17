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


# Kalshi sport tags that are left out of discovery: not sports in the usual sense (the person can change this).
DEFAULT_EXCLUDE_TAGS = "Esports,Video games,4th of July,Other"


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
    sports_discovery: bool
    sports_exclude_tags: tuple[str, ...]
    measured_min_games: int
    fetch_enabled: bool
    fetch_max_pages_per_run: int
    fetch_concurrency: int
    fetch_timeout_seconds: float
    fetch_max_bytes: int
    check_enabled: bool
    checker_model: str
    checker_reasoning_effort: str
    check_page_chars: int
    checker_max_output_tokens: int
    check_concurrency: int
    forecaster_model: str
    forecaster_reasoning_effort: str
    forecaster_max_output_tokens: int
    forecaster_count: int
    edge_min: float
    min_supported_claims: int
    min_ask_size: float
    min_research_shift: float
    edge_plausible_max: float
    opportunity_max_age_hours: float
    monitor_enabled: bool
    monitor_interval_minutes: float
    alert_move_cents: float
    alert_start_soon_minutes: float
    alert_cooldown_minutes: float
    alert_max_per_hour: int
    auto_research_max_per_day: int
    research_max_per_day: int  # games researched in the last 24 hours, whoever starts them; 0 = no limit
    auto_research_hours_ahead: float
    auto_research_min_gap_hours: float
    order_max_contracts: int
    order_max_cost_usd: float
    order_max_day_cost_usd: float
    order_expiry_minutes: float
    order_max_slippage_cents: float
    ticket_max_legs: int
    alerts_enabled: bool
    telegram_bot_token: str | None
    odds_enabled: bool
    odds_api_key: str | None
    odds_regions: str
    odds_cache_minutes: float
    telegram_chat_id: str | None
    record_baseline: bool
    resolve_after_hours: float

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
    sports_discovery = _parse_bool("SPORTS_DISCOVERY", env.get("SPORTS_DISCOVERY", "true"), problems)
    raw_exclude = env.get("SPORTS_EXCLUDE_TAGS")
    sports_exclude_tags = tuple(t.strip() for t in (DEFAULT_EXCLUDE_TAGS if raw_exclude is None or not raw_exclude.strip() else raw_exclude).split(",") if t.strip())
    measured_min_games = _parse_positive_int("MEASURED_MIN_GAMES", env.get("MEASURED_MIN_GAMES", "20"), problems)

    fetch_enabled = _parse_bool("FETCH_ENABLED", env.get("FETCH_ENABLED", "true"), problems)
    fetch_max_pages = _parse_positive_int(
        "FETCH_MAX_PAGES_PER_RUN", env.get("FETCH_MAX_PAGES_PER_RUN", "25"), problems
    )
    page_fetch_concurrency = _parse_positive_int("FETCH_CONCURRENCY", env.get("FETCH_CONCURRENCY", "5"), problems)
    fetch_timeout = _parse_positive_float(
        "FETCH_TIMEOUT_SECONDS", env.get("FETCH_TIMEOUT_SECONDS", "10"), problems
    )
    fetch_max_bytes = _parse_positive_int("FETCH_MAX_BYTES", env.get("FETCH_MAX_BYTES", "2000000"), problems)

    check_enabled = _parse_bool("CHECK_ENABLED", env.get("CHECK_ENABLED", "true"), problems)
    checker_model = env.get("CHECKER_MODEL", "gpt-5.4-mini").strip()
    if not checker_model:
        problems.append("CHECKER_MODEL must not be empty")
    checker_effort = env.get("CHECKER_REASONING_EFFORT", "medium").strip()
    if checker_effort not in EFFORTS:
        problems.append(f"CHECKER_REASONING_EFFORT must be one of {', '.join(EFFORTS)}, got {checker_effort!r}")
    check_page_chars = _parse_positive_int("CHECK_PAGE_CHARS", env.get("CHECK_PAGE_CHARS", "30000"), problems)
    checker_max_output = _parse_positive_int(
        "CHECKER_MAX_OUTPUT_TOKENS", env.get("CHECKER_MAX_OUTPUT_TOKENS", "4000"), problems
    )
    check_concurrency = _parse_positive_int("CHECK_CONCURRENCY", env.get("CHECK_CONCURRENCY", "5"), problems)

    forecaster_model = env.get("FORECASTER_MODEL", "gpt-5.4").strip()
    if not forecaster_model:
        problems.append("FORECASTER_MODEL must not be empty")
    forecaster_effort = env.get("FORECASTER_REASONING_EFFORT", "medium").strip()
    if forecaster_effort not in EFFORTS:
        problems.append(f"FORECASTER_REASONING_EFFORT must be one of {', '.join(EFFORTS)}, got {forecaster_effort!r}")
    forecaster_max_output = _parse_positive_int(
        "FORECASTER_MAX_OUTPUT_TOKENS", env.get("FORECASTER_MAX_OUTPUT_TOKENS", "8000"), problems
    )
    forecaster_count = _parse_positive_int("FORECASTER_COUNT", env.get("FORECASTER_COUNT", "3"), problems)
    if forecaster_count < 2:
        problems.append("FORECASTER_COUNT must be at least 2 (a median of one forecast is not a median)")

    edge_min = _parse_positive_float("EDGE_MIN", env.get("EDGE_MIN", "0.05"), problems)
    if edge_min >= 1:
        problems.append("EDGE_MIN is a probability gap in dollars per contract and must be below 1")
    min_supported_claims = _parse_positive_int("MIN_SUPPORTED_CLAIMS", env.get("MIN_SUPPORTED_CLAIMS", "5"), problems)
    min_ask_size = _parse_positive_float("MIN_ASK_SIZE", env.get("MIN_ASK_SIZE", "10"), problems)

    min_research_shift = _parse_positive_float("MIN_RESEARCH_SHIFT", env.get("MIN_RESEARCH_SHIFT", "0.05"), problems)
    edge_plausible_max = _parse_positive_float("EDGE_PLAUSIBLE_MAX", env.get("EDGE_PLAUSIBLE_MAX", "0.15"), problems)
    if min_research_shift >= 1 or edge_plausible_max >= 1:
        problems.append("MIN_RESEARCH_SHIFT and EDGE_PLAUSIBLE_MAX are probability gaps and must be below 1")
    if edge_plausible_max <= edge_min:
        problems.append("EDGE_PLAUSIBLE_MAX must be larger than EDGE_MIN, or no gap could ever be flagged")
    opportunity_max_age_hours = _parse_positive_float(
        "OPPORTUNITY_MAX_AGE_HOURS", env.get("OPPORTUNITY_MAX_AGE_HOURS", "12"), problems
    )
    monitor_enabled = _parse_bool("MONITOR_ENABLED", env.get("MONITOR_ENABLED", "false"), problems)
    monitor_interval = _parse_positive_float("MONITOR_INTERVAL_MINUTES", env.get("MONITOR_INTERVAL_MINUTES", "10"), problems)
    alert_move_cents = _parse_positive_float("ALERT_MOVE_CENTS", env.get("ALERT_MOVE_CENTS", "8"), problems)
    alert_start_soon = _parse_positive_float("ALERT_START_SOON_MINUTES", env.get("ALERT_START_SOON_MINUTES", "60"), problems)
    alert_cooldown = _parse_positive_float("ALERT_COOLDOWN_MINUTES", env.get("ALERT_COOLDOWN_MINUTES", "60"), problems)
    alert_max_per_hour = _parse_positive_int("ALERT_MAX_PER_HOUR", env.get("ALERT_MAX_PER_HOUR", "6"), problems)
    raw_auto = env.get("AUTO_RESEARCH_MAX_PER_DAY", "0").strip() or "0"
    if raw_auto.isdigit():
        auto_per_day = int(raw_auto)  # 0 is allowed and means off
    else:
        auto_per_day = 0
        problems.append(f"AUTO_RESEARCH_MAX_PER_DAY must be a whole number, 0 or more (0 means off), got {raw_auto!r}")
    raw_cap = env.get("RESEARCH_MAX_PER_DAY", "5").strip() or "5"
    if raw_cap.isdigit():
        research_cap = int(raw_cap)  # 0 is allowed and means no limit
    else:
        research_cap = 5
        problems.append(f"RESEARCH_MAX_PER_DAY must be a whole number, 0 or more (0 means no limit), got {raw_cap!r}")
    auto_hours_ahead = _parse_positive_float("AUTO_RESEARCH_HOURS_AHEAD", env.get("AUTO_RESEARCH_HOURS_AHEAD", "24"), problems)
    auto_min_gap = _parse_positive_float("AUTO_RESEARCH_MIN_GAP_HOURS", env.get("AUTO_RESEARCH_MIN_GAP_HOURS", "12"), problems)
    order_max_contracts = _parse_positive_int("ORDER_MAX_CONTRACTS", env.get("ORDER_MAX_CONTRACTS", "10"), problems)
    order_max_cost = _parse_positive_float("ORDER_MAX_COST_USD", env.get("ORDER_MAX_COST_USD", "5.00"), problems)
    order_max_day_cost = _parse_positive_float("ORDER_MAX_DAY_COST_USD", env.get("ORDER_MAX_DAY_COST_USD", "20.00"), problems)
    order_expiry = _parse_positive_float("ORDER_EXPIRY_MINUTES", env.get("ORDER_EXPIRY_MINUTES", "10"), problems)
    order_slippage = _parse_positive_float("ORDER_MAX_SLIPPAGE_CENTS", env.get("ORDER_MAX_SLIPPAGE_CENTS", "2"), problems)
    ticket_max_legs = _parse_positive_int("TICKET_MAX_LEGS", env.get("TICKET_MAX_LEGS", "20"), problems)
    if ticket_max_legs > 30:
        problems.append("TICKET_MAX_LEGS must be 30 or less")
    if order_max_day_cost < order_max_cost:
        problems.append("ORDER_MAX_DAY_COST_USD must not be smaller than ORDER_MAX_COST_USD")
    alerts_enabled = _parse_bool("ALERTS_ENABLED", env.get("ALERTS_ENABLED", "false"), problems)
    telegram_token = env.get("TELEGRAM_BOT_TOKEN", "").strip() or None
    telegram_chat = env.get("TELEGRAM_CHAT_ID", "").strip() or None
    if alerts_enabled:
        if not telegram_token or not telegram_chat:
            problems.append("ALERTS_ENABLED=true needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        if telegram_token and not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", telegram_token):
            problems.append("TELEGRAM_BOT_TOKEN does not look like a Telegram bot token (digits, a colon, then letters and digits)")
        if telegram_chat and not re.fullmatch(r"-?\d+", telegram_chat):
            problems.append("TELEGRAM_CHAT_ID must be a number (the chat id printed by the telegram-chat-id command)")
    odds_enabled = _parse_bool("ODDS_ENABLED", env.get("ODDS_ENABLED", "false"), problems)
    odds_api_key = env.get("ODDS_API_KEY", "").strip() or None
    odds_regions = env.get("ODDS_REGIONS", "eu").strip()
    odds_cache_minutes = _parse_positive_float("ODDS_CACHE_MINUTES", env.get("ODDS_CACHE_MINUTES", "10"), problems)
    if odds_enabled:
        if not odds_api_key:
            problems.append("ODDS_ENABLED=true needs ODDS_API_KEY")
        elif not re.fullmatch(r"[A-Za-z0-9]{16,64}", odds_api_key):
            problems.append("ODDS_API_KEY does not look like a The Odds API key (letters and digits)")
        if not re.fullmatch(r"(us|us2|uk|eu|au)(,(us|us2|uk|eu|au))*", odds_regions):
            problems.append("ODDS_REGIONS must be a comma separated list of us, us2, uk, eu, au")
    record_baseline = _parse_bool("RECORD_BASELINE", env.get("RECORD_BASELINE", "true"), problems)
    resolve_after_hours = _parse_positive_float("RESOLVE_AFTER_HOURS", env.get("RESOLVE_AFTER_HOURS", "3"), problems)

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

    log.info("The bookmaker benchmark is %s." % (f"ON (regions {odds_regions})" if odds_enabled else "off (ODDS_ENABLED is not 'true')"))
    log.info("Alerts are %s." % ("sent to a Telegram chat" if alerts_enabled else "only recorded in the app (ALERTS_ENABLED is not 'true')"))
    log.info(
        "Research is limited to %s.", f"{research_cap} games in any 24 hours (RESEARCH_MAX_PER_DAY)" if research_cap else "no number of games (RESEARCH_MAX_PER_DAY is 0)")
    if monitor_enabled:
        log.info(
            "The watcher is ON (every %g min). Alerts are %s. Automatic research: %s.",
            monitor_interval, "sent to Telegram and recorded in the app" if alerts_enabled else "only recorded in the app",
            f"up to {auto_per_day} games a day" if auto_per_day else "off",
        )
    else:
        log.info("The watcher is off (MONITOR_ENABLED is not 'true'): no alerts are made and nothing is researched automatically.")

    log.info(
        "Games list: %d measured series configured (%s); discovery of all other Kalshi sports is %s.", len(sports_series),
        "from SPORTS_SERIES" if raw_series is not None else "default list; set SPORTS_SERIES to change it",
        "ON (SPORTS_EXCLUDE_TAGS: %s)" % ", ".join(sports_exclude_tags) if sports_discovery else "off (SPORTS_DISCOVERY is not 'true')",
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
        sports_discovery=sports_discovery,
        sports_exclude_tags=sports_exclude_tags,
        measured_min_games=measured_min_games,
        fetch_enabled=fetch_enabled,
        fetch_max_pages_per_run=fetch_max_pages,
        fetch_concurrency=page_fetch_concurrency,
        fetch_timeout_seconds=fetch_timeout,
        fetch_max_bytes=fetch_max_bytes,
        check_enabled=check_enabled,
        checker_model=checker_model,
        checker_reasoning_effort=checker_effort,
        check_page_chars=check_page_chars,
        checker_max_output_tokens=checker_max_output,
        check_concurrency=check_concurrency,
        forecaster_model=forecaster_model,
        forecaster_reasoning_effort=forecaster_effort,
        forecaster_max_output_tokens=forecaster_max_output,
        forecaster_count=forecaster_count,
        edge_min=edge_min,
        min_supported_claims=min_supported_claims,
        min_ask_size=min_ask_size,
        min_research_shift=min_research_shift,
        edge_plausible_max=edge_plausible_max,
        opportunity_max_age_hours=opportunity_max_age_hours,
        monitor_enabled=monitor_enabled,
        monitor_interval_minutes=monitor_interval,
        alert_move_cents=alert_move_cents,
        alert_start_soon_minutes=alert_start_soon,
        alert_cooldown_minutes=alert_cooldown,
        alert_max_per_hour=alert_max_per_hour,
        auto_research_max_per_day=auto_per_day,
        research_max_per_day=research_cap,
        auto_research_hours_ahead=auto_hours_ahead,
        auto_research_min_gap_hours=auto_min_gap,
        order_max_contracts=order_max_contracts,
        order_max_cost_usd=order_max_cost,
        order_max_day_cost_usd=order_max_day_cost,
        order_expiry_minutes=order_expiry,
        order_max_slippage_cents=order_slippage,
        ticket_max_legs=ticket_max_legs,
        alerts_enabled=alerts_enabled,
        telegram_bot_token=telegram_token,
        odds_enabled=odds_enabled,
        odds_api_key=odds_api_key,
        odds_regions=odds_regions,
        odds_cache_minutes=odds_cache_minutes,
        telegram_chat_id=telegram_chat,
        record_baseline=record_baseline,
        resolve_after_hours=resolve_after_hours,
    )
