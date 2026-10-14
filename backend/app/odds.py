"""Bookmaker odds from The Odds API, used only as a benchmark that is saved next to each forecast.

The API key is a secret: it sits in the URL of every call, so it is kept in settings only, is never logged (a log
filter hides it from the HTTP library's own log lines) and never appears in an error that reaches a page: a failure
is reported by a kind of error, not by its text. Nothing here is a trading call; it only reads prices.

A bookmaker price is only ever attached to a game when exactly one game of the feed matches by both team names and
start time. A game that does not match gets no price and a reason, never a guess."""

import asyncio
import logging
import re
import statistics
import time
import unicodedata
from datetime import UTC, datetime, timedelta

import httpx2

API = "https://api.the-odds-api.com/v4"
KEY_IN_TEXT = re.compile(r"apiKey=[^&\s'\"]+")
LOW_CREDITS = 50
MATCH_WINDOW = timedelta(hours=3)  # a game of the feed must start this close to the Kalshi start
MIN_BOOKS = 3  # fewer bookmakers than this is not a consensus
ACTIVE_CACHE_SECONDS = 3600  # the list of active sports is free to read and changes slowly
OUT_OF_CREDITS_WAIT = 3600  # after the credits ran out, do not call again for this long

log = logging.getLogger("app.odds")

# Kalshi series -> The Odds API sport key. Tennis keys exist per tournament and only while it runs, so they are looked up
# among the active keys; the Challenger tours have no key at all (checked 2026-10-14).
SERIES_KEYS = {
    "KXEPLGAME": "soccer_epl", "KXUCLGAME": "soccer_uefa_champs_league", "KXUELGAME": "soccer_uefa_europa_league",
    "KXMLSGAME": "soccer_usa_mls", "KXLALIGAGAME": "soccer_spain_la_liga", "KXSERIEAGAME": "soccer_italy_serie_a",
    "KXBUNDESLIGAGAME": "soccer_germany_bundesliga", "KXLIGUE1GAME": "soccer_france_ligue_one",
    "KXMLBGAME": "baseball_mlb", "KXNPBGAME": "baseball_npb", "KXKBOGAME": "baseball_kbo",
}
TENNIS_PREFIX = {"KXATPMATCH": "tennis_atp_", "KXWTAMATCH": "tennis_wta_"}
EXCHANGES = ("betfair_ex", "smarkets", "matchbook", "betdaq")  # exchange prices carry a commission, not a margin: not part of the consensus

# Words to drop and names the feed spells differently; extended when a real game fails to match (the match rate is printed).
STOP_WORDS = {"fc", "cf", "afc", "ac", "sc", "fk", "sk", "club", "de", "the", "of", "vs", "bk"}
NAME_FIXES = {"psg": "paris saint germain", "bodoe": "bodo", "rb": "red bulls"}


class OddsError(Exception):
    """Odds could not be read. The class name says what happened; the text never holds the key."""


class OddsUnauthorized(OddsError):
    """The key is wrong."""


class OddsOutOfCredits(OddsError):
    """The credits of the plan are used up."""


class OddsRateLimited(OddsError):
    """Too many requests too fast."""


class OddsNetworkError(OddsError):
    """The service could not be reached."""


class _HideKey(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The library passes the URL as an object, not a string, so the arguments cannot be masked one by one: the
        # finished message is.
        record.msg = KEY_IN_TEXT.sub("apiKey=<hidden>", record.getMessage())
        record.args = None
        return True


def hide_key_in_logs() -> None:
    """The HTTP libraries log every request line, URL included. Call once at start-up."""
    for name in ("httpx2", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _HideKey) for f in logger.filters):
            logger.addFilter(_HideKey())


class OddsClient:
    def __init__(self, key: str, regions: str, cache_minutes: float, client: httpx2.AsyncClient | None = None, clock=time.monotonic):
        self._key, self._regions, self._cache_seconds = key, regions, cache_minutes * 60
        self._client, self._clock = client, clock
        self._cache: dict[str, tuple[float, list]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._blocked_until = 0.0
        self.credits_remaining: int | None = None

    async def _get(self, path: str, params: dict) -> list:
        if self._clock() < self._blocked_until:
            raise OddsOutOfCredits("the credits ran out; not calling again for a while")
        params = {**params, "apiKey": self._key}
        try:
            if self._client is not None:
                response = await self._client.get(f"{API}{path}", params=params)
            else:
                async with httpx2.AsyncClient(timeout=20) as client:
                    response = await client.get(f"{API}{path}", params=params)
        except httpx2.HTTPError as exc:
            raise OddsNetworkError(f"the odds service could not be reached ({type(exc).__name__})") from None
        left = response.headers.get("x-requests-remaining")
        if left is not None and left.isdigit():
            self.credits_remaining = int(left)
            if self.credits_remaining == 0:
                self._blocked_until = self._clock() + OUT_OF_CREDITS_WAIT
                log.warning("The Odds API credits are used up; no odds are read for the next hour.")
            elif self.credits_remaining < LOW_CREDITS:
                log.warning("The Odds API has only %d credits left this month.", self.credits_remaining)
        if response.status_code == 401:
            try:
                code = response.json().get("error_code")
            except ValueError:
                code = None
            raise (OddsOutOfCredits if code == "OUT_OF_USAGE_CREDITS" else OddsUnauthorized)(f"the odds service answered HTTP {response.status_code}")
        if response.status_code == 429:
            raise OddsRateLimited(f"the odds service answered HTTP {response.status_code}")
        if response.status_code != 200:
            raise OddsError(f"the odds service answered HTTP {response.status_code}")
        return response.json()

    async def _cached(self, name: str, seconds: float, load) -> list:
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:  # two runs of one league at the same moment cost one call
            hit = self._cache.get(name)
            if hit and self._clock() - hit[0] < seconds:
                return hit[1]
            value = await load()
            self._cache[name] = (self._clock(), value)
            return value

    async def active_sport_keys(self) -> set[str]:
        """Free to read (no credits)."""
        sports = await self._cached("sports", ACTIVE_CACHE_SECONDS, lambda: self._get("/sports", {}))
        return {s["key"] for s in sports if s.get("active")}

    async def odds(self, sport_key: str) -> list[dict]:
        """Head-to-head prices of the upcoming games of one sport key: one credit per region."""
        return await self._cached(
            sport_key, self._cache_seconds,
            lambda: self._get(f"/sports/{sport_key}/odds", {"regions": self._regions, "markets": "h2h", "oddsFormat": "decimal"}))


# ---- matching a game of ours to a game of the feed -------------------------------------------------------

def _tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).replace("ø", "o").replace("ß", "ss").replace("ł", "l")
    text = re.sub(r"[.'’]", "", text)
    out: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text):
        out += NAME_FIXES.get(token, token).split()
    return [t for t in out if t not in STOP_WORDS]


def _covers(x: list[str], y: list[str]) -> bool:
    """Every word of x is a word of y or the start of one ("d" starts "dodgers")."""
    return bool(x) and all(any(w == v or v.startswith(w) for v in y) for w in x)


def same_team(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return _covers(ta, tb) or _covers(tb, ta)


def sport_keys_for(series_ticker: str, active: set[str]) -> list[str]:
    """The feed's sport keys that can hold a game of this series (only keys that are active, to spare credits)."""
    if series_ticker in SERIES_KEYS:
        return [SERIES_KEYS[series_ticker]] if SERIES_KEYS[series_ticker] in active else []
    if series_ticker in TENNIS_PREFIX:
        return sorted(k for k in active if k.startswith(TENNIS_PREFIX[series_ticker]))
    return []


def _teams_of(title: str) -> tuple[str, str] | None:
    parts = title.split(":", 1)[-1].split(" vs ")
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def find_game(events: list[dict], title: str, starts_at: datetime | None) -> tuple[dict | None, str | None]:
    """The one game of the feed with both teams and a start within three hours; otherwise a reason."""
    teams = _teams_of(title)
    if teams is None or starts_at is None:
        return None, "the game title or start time could not be read"
    found = []
    for event in events:
        start = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        if abs(start - starts_at) > MATCH_WINDOW:
            continue
        h, a = event["home_team"], event["away_team"]
        if (same_team(teams[0], h) and same_team(teams[1], a)) or (same_team(teams[0], a) and same_team(teams[1], h)):
            found.append(event)
    if len(found) == 1:
        return found[0], None
    return None, "no game of the odds feed matched by team names and start time" if not found else "several games of the odds feed matched"


# ---- the price ---------------------------------------------------------------------------------------------

def book_prices(event: dict, expected_outcomes: int) -> dict[str, dict]:
    """Per outcome name of the feed: the consensus probability (median over bookmakers of the prices with the margin
    removed by scaling to 1, exchanges left out), Pinnacle's own, and how many bookmakers were used."""
    per_book: dict[str, dict[str, float]] = {}
    for book in event.get("bookmakers", []):
        market = next((m for m in book.get("markets", []) if m.get("key") == "h2h"), None)
        if market is None or len(market["outcomes"]) != expected_outcomes or any(o["price"] <= 1 for o in market["outcomes"]):
            continue
        raw = {o["name"]: 1 / o["price"] for o in market["outcomes"]}
        total = sum(raw.values())
        per_book[book["key"]] = {name: p / total for name, p in raw.items()}
    used = {k: v for k, v in per_book.items() if not k.startswith(EXCHANGES)}
    out = {}
    for name in {n for v in used.values() for n in v}:
        values = [v[name] for v in used.values() if name in v]
        out[name] = {
            "probability": statistics.median(values), "count": len(values),
            "pinnacle": per_book.get("pinnacle", {}).get(name),
        }
    return out


async def book_for_game(client: OddsClient | None, *, event_ticker: str, title: str, starts_at: datetime | None,
                        outcome_names: list[str], outcome_tickers: list[str]) -> dict:
    """{"at": when it was read, "by_ticker": {market ticker: {probability, pinnacle, count}}, "note": why not}.
    Never raises: a failure is a note on the record, logged here, and the forecast is saved without a bookmaker price."""
    now = datetime.now(UTC)
    if client is None:
        return {"at": None, "by_ticker": {}, "note": "the bookmaker benchmark is off (ODDS_ENABLED is not true)"}
    try:
        series = event_ticker.split("-")[0]
        keys = sport_keys_for(series, await client.active_sport_keys())
        if not keys:
            return {"at": None, "by_ticker": {}, "note": "no bookmaker source for this league (the odds feed has no active sport for it)"}
        event, why = None, None
        for key in keys:
            event, why = find_game(await client.odds(key), title, starts_at)
            if event:
                break
        if event is None:
            return {"at": now, "by_ticker": {}, "note": why}
        prices = book_prices(event, len(outcome_tickers))
        by_ticker = {}
        for name, ticker in zip(outcome_names, outcome_tickers):
            feed_name = "Draw" if name.strip().lower() in ("tie", "draw") else next(
                (n for n in (event["home_team"], event["away_team"]) if same_team(name, n)), None)
            hit = prices.get(feed_name) if feed_name else None
            if hit and hit["count"] >= MIN_BOOKS:
                by_ticker[ticker] = hit
        if len(by_ticker) != len(outcome_tickers):
            return {"at": now, "by_ticker": {}, "note": f"fewer than {MIN_BOOKS} bookmakers priced every outcome, or an outcome name did not match"}
        return {"at": now, "by_ticker": by_ticker, "note": None}
    except OddsError as exc:
        log.warning("Bookmaker odds unavailable for %s: %s", event_ticker, exc)
        return {"at": None, "by_ticker": {}, "note": f"bookmaker odds could not be read ({type(exc).__name__})"}
