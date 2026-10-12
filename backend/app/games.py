"""The games list: one entry per game or match, from a configured list of Kalshi series.

Kalshi has no "sports games" filter, and fetching everything is far too slow, so the series to show
come from the SPORTS_SERIES setting. Each series is fetched in parallel (a few at a time) and the
combined result is kept in memory for a short while.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.auth import require_user
from app.config import SeriesEntry, Settings
from app.kalshi import KalshiClient

log = logging.getLogger("app.games")

ERROR_CACHE_SECONDS = 10  # a result with a failed league is retried soon, not kept for a minute
MAX_PAGES_PER_SERIES = 5


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_game(event: dict[str, Any], entry: SeriesEntry) -> dict[str, Any] | None:
    markets = event.get("markets") or []
    if not markets:
        return None
    starts = [t for t in (_parse_time(m.get("occurrence_datetime")) for m in markets) if t]
    closes = [t for t in (_parse_time(m.get("close_time")) for m in markets) if t]
    return {
        "event_ticker": event["event_ticker"],
        "title": event.get("title") or event["event_ticker"],
        "sub_title": event.get("sub_title") or None,
        "sport": entry.sport,
        "league": entry.league,
        "starts_at": min(starts).isoformat() if starts else None,
        "closes_at": min(closes).isoformat() if closes else None,
        "outcomes": [
            {
                "market_ticker": m["ticker"],
                "label": m.get("yes_sub_title") or m.get("title") or m["ticker"],
                "bid": m.get("yes_bid_dollars"),
                "ask": m.get("yes_ask_dollars"),
                "last": m.get("last_price_dollars"),
                "volume": m.get("volume_fp"),
                "status": m.get("status"),
            }
            for m in markets
        ],
    }


class GamesService:
    def __init__(
        self,
        get_kalshi: Callable[[], KalshiClient],
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._get_kalshi = get_kalshi
        self._settings = settings
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._cache: tuple[float, dict[str, Any]] | None = None

    def _fetch_series(self, entry: SeriesEntry) -> list[dict[str, Any]]:
        kalshi = self._get_kalshi()
        games, cursor = [], None
        for _ in range(MAX_PAGES_PER_SERIES):
            page = kalshi.list_events(
                series_ticker=entry.ticker, status="open", limit=200, with_nested_markets=True, cursor=cursor
            )
            for event in page.get("events", []):
                game = build_game(event, entry)
                if game:
                    games.append(game)
            cursor = page.get("cursor")
            if not cursor:
                break
        return games

    def _refresh(self) -> dict[str, Any]:
        entries = self._settings.sports_series
        games: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        def one(entry: SeriesEntry):
            try:
                return entry, self._fetch_series(entry), None
            except Exception as exc:  # one league failing must not hide the others; it is reported
                log.warning("Games list: series %s failed: %s", entry.ticker, exc)
                return entry, [], f"{type(exc).__name__}: {exc}"

        started = self._clock()
        with ThreadPoolExecutor(max_workers=self._settings.sports_fetch_concurrency) as pool:
            for entry, found, error in pool.map(one, entries):
                games += found
                if error:
                    errors.append({"series": entry.ticker, "league": entry.league, "error": error})
        log.info("Games list refreshed: %d games from %d series in %.1fs, %d series failed",
                 len(games), len(entries), self._clock() - started, len(errors))
        return {"games": games, "errors": errors, "fetched_at": self._now().isoformat()}

    def get(self) -> dict[str, Any]:
        # One lock: simultaneous page loads wait for a single refresh instead of each starting one.
        with self._lock:
            if self._cache and self._clock() < self._cache[0]:
                return self._cache[1]
            payload = self._refresh()
            ttl = ERROR_CACHE_SECONDS if payload["errors"] else self._settings.games_cache_seconds
            self._cache = (self._clock() + ttl, payload)
            return payload

    def query(
        self, sport: str | None = None, q: str | None = None, limit: int = 200, include_started: bool = False
    ) -> dict[str, Any]:
        payload = self.get()
        now = self._now()
        games = []
        hidden_started = 0
        for g in payload["games"]:
            if sport and g["sport"].lower() != sport.lower():
                continue
            if q and q.lower() not in f"{g['title']} {g['league']}".lower():
                continue
            starts = _parse_time(g["starts_at"])
            started = bool(starts and starts <= now)
            if started and not include_started:
                hidden_started += 1  # already played or in play; Kalshi keeps them open until they settle
                continue
            games.append({**g, "started": started})
        games.sort(key=lambda g: (g["starts_at"] is None, g["starts_at"] or ""))
        sports = list(dict.fromkeys(e.sport for e in self._settings.sports_series))
        return {
            "games": games[:limit],
            "total": len(games),
            "hidden_started": hidden_started,
            "sports": sports,
            "errors": payload["errors"],
            "fetched_at": payload["fetched_at"],
        }


router = APIRouter(prefix="/api", tags=["games"], dependencies=[Depends(require_user)])


@router.get("/games")
def list_games(
    request: Request,
    sport: Annotated[str | None, Query(max_length=40)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    include_started: bool = False,
):
    return request.app.state.games.query(sport=sport, q=q, limit=limit, include_started=include_started)
