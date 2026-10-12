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
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.auth import require_user
from app.config import SeriesEntry, Settings
from app.kalshi import KalshiClient

log = logging.getLogger("app.games")

ERROR_CACHE_SECONDS = 10  # a result with a failed league is retried soon, not kept for a minute
MAX_PAGES_PER_SERIES = 5
MILESTONES_CACHE_SECONDS = 600  # kickoff times rarely change
MILESTONES_LOOKBACK_HOURS = 48  # Kalshi keeps games open after they start, until they settle
MAX_MILESTONE_PAGES = 10
START_TIMES_NOTE = "Start times are unavailable right now, so games show no start time. Reload to try again."


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_game(
    event: dict[str, Any], entry: SeriesEntry, start_times: dict[str, str] | None = None
) -> dict[str, Any] | None:
    markets = event.get("markets") or []
    if not markets:
        return None
    # The start comes from Kalshi's milestones only. A market's occurrence_datetime is the expected
    # settlement time (hours after kickoff), so it is never used as a start time.
    start = _parse_time((start_times or {}).get(event["event_ticker"]))
    closes = [t for t in (_parse_time(m.get("close_time")) for m in markets) if t]
    return {
        "event_ticker": event["event_ticker"],
        "title": event.get("title") or event["event_ticker"],
        "sub_title": event.get("sub_title") or None,
        "sport": entry.sport,
        "league": entry.league,
        "starts_at": start.isoformat() if start else None,
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
        self._start_cache: tuple[float, dict[str, str] | None, str | None] | None = None

    def _fetch_start_times(self) -> dict[str, str]:
        """Real kickoff time per event ticker, from all sports milestones that start from 48 hours back."""
        since = (self._now() - timedelta(hours=MILESTONES_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        kalshi = self._get_kalshi()
        times: dict[str, str] = {}
        cursor = None
        for _ in range(MAX_MILESTONE_PAGES):
            page = kalshi.list_milestones(category="Sports", minimum_start_date=since, limit=500, cursor=cursor)
            for m in page.get("milestones", []):
                start = m.get("start_date")
                for ticker in (m.get("primary_event_tickers") or []) + (m.get("related_event_tickers") or []):
                    if start and (ticker not in times or start < times[ticker]):
                        times[ticker] = start  # earliest start wins if a ticker is listed twice
            cursor = page.get("cursor")
            if not cursor:
                break
        return times

    def _start_times_if_needed(self):
        """Returns (times or None, error or None), using the 10 minute cache. Called under the lock."""
        if self._start_cache and self._clock() < self._start_cache[0]:
            return self._start_cache[1], self._start_cache[2]
        try:
            times, error = self._fetch_start_times(), None
        except Exception as exc:  # reported on the page; start times stay empty rather than wrong
            log.warning("Games list: start times failed: %s", exc)
            times, error = None, f"{type(exc).__name__}: {exc}"
        ttl = ERROR_CACHE_SECONDS if error else MILESTONES_CACHE_SECONDS
        self._start_cache = (self._clock() + ttl, times, error)
        return times, error

    def _fetch_series(self, entry: SeriesEntry) -> list[dict[str, Any]]:
        """The open events of one series (raw, with their markets)."""
        kalshi = self._get_kalshi()
        events: list[dict[str, Any]] = []
        cursor = None
        for _ in range(MAX_PAGES_PER_SERIES):
            page = kalshi.list_events(
                series_ticker=entry.ticker, status="open", limit=200, with_nested_markets=True, cursor=cursor
            )
            events += page.get("events", [])
            cursor = page.get("cursor")
            if not cursor:
                break
        return events

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
        # Start times get their own worker so the series never exceed SPORTS_FETCH_CONCURRENCY, and load
        # at the same time as the series (usually they come from the 10 minute cache).
        with ThreadPoolExecutor(max_workers=1) as start_pool, \
                ThreadPoolExecutor(max_workers=self._settings.sports_fetch_concurrency) as pool:
            start_future = start_pool.submit(self._start_times_if_needed)
            fetched = list(pool.map(one, entries))
            start_times, start_error = start_future.result()
        for entry, events, error in fetched:
            for event in events:
                game = build_game(event, entry, start_times)
                if game:
                    games.append(game)
            if error:
                errors.append({"series": entry.ticker, "league": entry.league, "error": error})
        notes = [START_TIMES_NOTE] if start_error else []
        log.info("Games list refreshed: %d games from %d series in %.1fs, %d series failed%s",
                 len(games), len(entries), self._clock() - started, len(errors),
                 ", start times unavailable" if start_error else "")
        return {"games": games, "errors": errors, "notes": notes, "fetched_at": self._now().isoformat()}

    def get(self) -> dict[str, Any]:
        # One lock: simultaneous page loads wait for a single refresh instead of each starting one.
        with self._lock:
            if self._cache and self._clock() < self._cache[0]:
                return self._cache[1]
            payload = self._refresh()
            ttl = ERROR_CACHE_SECONDS if payload["errors"] or payload["notes"] else self._settings.games_cache_seconds
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
            "notes": payload["notes"],
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
