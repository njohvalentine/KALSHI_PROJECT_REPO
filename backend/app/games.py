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
from app.discovery import MAX_DISCOVERED_SERIES, SeriesCatalog, upcoming_series
from app.kalshi import KalshiClient

log = logging.getLogger("app.games")

ERROR_CACHE_SECONDS = 10  # a result with a failed league is retried soon, not kept for a minute
MAX_PAGES_PER_SERIES = 5
MILESTONES_CACHE_SECONDS = 600  # kickoff times rarely change
DISCOVERY_LOOKBACK_HOURS = 6  # a game that started within this time still counts as coming up for the sports list
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
                "ask_size": m.get("yes_ask_size_fp"),  # contracts offered at the best ask / best bid (for the free bookmaker check)
                "bid_size": m.get("yes_bid_size_fp"),
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
        measured: Callable[[], dict[str, int]] | None = None,
    ):
        self._get_kalshi = get_kalshi
        self._settings = settings
        self._clock = clock
        self._now = now
        self._measured = measured  # scored games per sport, from the database; None in tests that do not need it
        self._lock = threading.Lock()
        self._caches: dict[str, tuple[float, dict[str, Any]]] = {}  # by scope: "" is the measured series, else a sport
        self._start_cache: tuple[float, tuple[dict[str, str], dict[str, int]] | None, str | None] | None = None
        self._catalog = SeriesCatalog(get_kalshi, settings.sports_exclude_tags, clock)

    def entry_of(self, series_ticker: str | None) -> SeriesEntry | None:
        """The sport and league of a series: the configured (measured) series first, then the discovered ones."""
        configured = next((e for e in self._settings.sports_series if e.ticker == series_ticker), None)
        if configured or not self._settings.sports_discovery:
            return configured
        try:
            return self._catalog.entry_of(series_ticker)
        except Exception as exc:  # the run goes on with no sport rather than failing on a catalog problem
            log.warning("Sports catalog unavailable for %s: %s", series_ticker, exc)
            return None

    def _fetch_start_times(self) -> tuple[dict[str, str], dict[str, int]]:
        """Real kickoff time per event ticker, from all sports milestones that start from 48 hours back, and the number of
        upcoming games per series (the same milestones: discovery costs no extra call)."""
        since = (self._now() - timedelta(hours=MILESTONES_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        kalshi = self._get_kalshi()
        times: dict[str, str] = {}
        milestones: list[dict[str, Any]] = []
        cursor = None
        for _ in range(MAX_MILESTONE_PAGES):
            page = kalshi.list_milestones(category="Sports", minimum_start_date=since, limit=500, cursor=cursor)
            milestones += page.get("milestones", [])
            for m in page.get("milestones", []):
                start = m.get("start_date")
                for ticker in (m.get("primary_event_tickers") or []) + (m.get("related_event_tickers") or []):
                    if start and (ticker not in times or start < times[ticker]):
                        times[ticker] = start  # earliest start wins if a ticker is listed twice
            cursor = page.get("cursor")
            if not cursor:
                break
        recent = (self._now() - timedelta(hours=DISCOVERY_LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return times, upcoming_series(milestones, recent)

    def _milestones_if_needed(self):
        """Returns ((times, series counts) or None, error or None), using the 10 minute cache. Called under the lock."""
        if self._start_cache and self._clock() < self._start_cache[0]:
            return self._start_cache[1], self._start_cache[2]
        try:
            found, error = self._fetch_start_times(), None
        except Exception as exc:  # reported on the page; start times stay empty rather than wrong
            log.warning("Games list: start times failed: %s", exc)
            found, error = None, f"{type(exc).__name__}: {exc}"
        ttl = ERROR_CACHE_SECONDS if error else MILESTONES_CACHE_SECONDS
        self._start_cache = (self._clock() + ttl, found, error)
        return found, error

    def _start_times_if_needed(self):
        found, error = self._milestones_if_needed()
        return (found[0] if found else None), error

    def _discovered(self) -> tuple[list[tuple[SeriesEntry, int]], str | None]:
        """Series that are not configured but have games coming up: [(entry, upcoming games)], busiest first, and the
        reason when they could not be found. Called under the lock."""
        if not self._settings.sports_discovery:
            return [], None
        found, error = self._milestones_if_needed()
        if found is None:
            return [], None  # the same failure is already on the page as the start times note
        try:
            catalog = self._catalog.entries()
        except Exception as exc:
            log.warning("Games list: the sports catalog failed: %s", exc)
            return [], f"Other sports could not be discovered right now ({type(exc).__name__})."
        configured = {e.ticker for e in self._settings.sports_series}
        out = [(catalog[t], n) for t, n in found[1].items() if t in catalog and t not in configured]
        return sorted(out, key=lambda x: -x[1]), None

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

    def _refresh(self, entries, extra_notes: list[str] | None = None) -> dict[str, Any]:
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
        notes = ([START_TIMES_NOTE] if start_error else []) + (extra_notes or [])
        log.info("Games list refreshed: %d games from %d series in %.1fs, %d series failed%s",
                 len(games), len(entries), self._clock() - started, len(errors),
                 ", start times unavailable" if start_error else "")
        return {"games": games, "errors": errors, "notes": notes, "fetched_at": self._now().isoformat()}

    def get(self, sport: str | None = None) -> dict[str, Any]:
        """The games of the measured series (`sport` None) or of one sport including its discovered series."""
        scope = (sport or "").lower()
        # One lock: simultaneous page loads wait for a single refresh instead of each starting one.
        with self._lock:
            hit = self._caches.get(scope)
            if hit and self._clock() < hit[0]:
                return hit[1]
            entries, notes = list(self._settings.sports_series), []
            if sport:
                entries = [e for e in entries if e.sport.lower() == scope]
                found, why = self._discovered()
                extra = [e for e, _ in found if e.sport.lower() == scope]
                if why:
                    notes.append(why)
                if len(extra) > MAX_DISCOVERED_SERIES:
                    notes.append(f"{len(extra)} series of this sport have games coming up; showing the {MAX_DISCOVERED_SERIES} with the most games.")
                entries += extra[:MAX_DISCOVERED_SERIES]
            payload = self._refresh(entries, notes)
            ttl = ERROR_CACHE_SECONDS if payload["errors"] or payload["notes"] else self._settings.games_cache_seconds
            self._caches[scope] = (self._clock() + ttl, payload)
            return payload

    def more_sports(self) -> tuple[list[dict[str, Any]], str | None]:
        """Sports (and extra leagues of configured sports) Kalshi offers beyond the measured series, with the number of
        games coming up: [{"sport", "games", "series", "also_measured"}], and the reason when discovery failed."""
        with self._lock:
            found, why = self._discovered()
        configured_sports = {e.sport.lower() for e in self._settings.sports_series}
        by_sport: dict[str, dict[str, Any]] = {}
        for entry, n in found:
            item = by_sport.setdefault(entry.sport, {"sport": entry.sport, "games": 0, "series": 0, "also_measured": entry.sport.lower() in configured_sports})
            item["games"] += n
            item["series"] += 1
        return sorted(by_sport.values(), key=lambda i: -i["games"]), why

    def query(
        self, sport: str | None = None, q: str | None = None, limit: int = 200, include_started: bool = False, more: bool = False
    ) -> dict[str, Any]:
        """`more` loads the sport's discovered series as well (slower: the first load asks Kalshi about each of them)."""
        payload = self.get(sport if more and sport and self._settings.sports_discovery else None)
        now = self._now()
        scored = (self._measured() if self._measured else {})
        minimum = self._settings.measured_min_games
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
            games.append({**g, "started": started, "measured": scored.get(g["sport"], 0) >= minimum, "scored_games": scored.get(g["sport"], 0)})
        games.sort(key=lambda g: (g["starts_at"] is None, g["starts_at"] or ""))
        sports = list(dict.fromkeys(e.sport for e in self._settings.sports_series))
        more_sports, more_note = self.more_sports()
        return {
            "games": games[:limit],
            "total": len(games),
            "hidden_started": hidden_started,
            "sports": sports,
            "errors": payload["errors"],
            "notes": payload["notes"] + ([more_note] if more_note else []),
            "more_sports": more_sports,
            "measured_min_games": minimum,
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
    more: bool = False,
):
    state = request.app.state
    return {**state.games.query(sport=sport, q=q, limit=limit, include_started=include_started, more=more),
            "screening": {"available": state.odds is not None, "max_leagues": state.settings.screen_max_leagues}}  # the free bookmaker check needs the odds feed
