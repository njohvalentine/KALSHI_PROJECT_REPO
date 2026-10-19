"""Read-only client for Kalshi's public market data. No credentials are used or needed.

Responses are returned as Kalshi sends them (parsed JSON), so this file does not guess field names.
Retries are visible: every retry is logged with its reason, and the client gives up after a fixed
number of tries (CLAUDE.md Module 4).
"""

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx2

log = logging.getLogger("app.kalshi")


class KalshiError(Exception):
    """Kalshi could not be reached, kept rate limiting us, or returned an error."""


class KalshiNotFound(KalshiError):
    pass


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


class KalshiClient:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx2.Client | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        # Limits sized for slow networks: on a VPN a connection took 1.6 s and one events page 5 s.
        # They are also short enough that an unreachable Kalshi shows an error in about 20 s, not a minute.
        self._client = client or httpx2.Client(timeout=httpx2.Timeout(20.0, connect=6.0))
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_reason = "no attempt made"
        for attempt in range(1, self._max_attempts + 1):
            wait = self._backoff * 2 ** (attempt - 1)
            started = time.monotonic()
            try:
                response = self._client.get(url, params=_clean(params or {}))
            except httpx2.TransportError as exc:
                last_reason = f"connection problem: {type(exc).__name__}"
            else:
                if response.status_code == 429:
                    last_reason = "rate limited (HTTP 429)"
                    retry_after = response.headers.get("retry-after", "")
                    if retry_after.isdigit():
                        wait = max(wait, float(retry_after))
                elif response.status_code == 404:
                    raise KalshiNotFound(f"Kalshi returned 404 for {path}")
                elif response.status_code >= 400:
                    raise KalshiError(f"Kalshi returned HTTP {response.status_code} for {path}")
                else:
                    # Shows where page load time goes: read it with `docker compose logs backend`.
                    log.info("Kalshi GET %s answered %d in %.0f ms", path, response.status_code, (time.monotonic() - started) * 1000)
                    return response.json()
            if attempt < self._max_attempts:
                log.warning(
                    "Kalshi retry %d/%d for %s after %s; waiting %.1fs",
                    attempt, self._max_attempts - 1, path, last_reason, wait,
                )
                self._sleep(wait)
        raise KalshiError(f"Giving up on {path} after {self._max_attempts} tries: {last_reason}")

    # Current markets
    def list_markets(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        tickers: str | None = None,
        mve_filter: str | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        min_settled_ts: int | None = None,
        max_settled_ts: int | None = None,
    ) -> dict[str, Any]:
        return self._get("/markets", dict(
            status=status, limit=limit, cursor=cursor, event_ticker=event_ticker,
            series_ticker=series_ticker, tickers=tickers, mve_filter=mve_filter, min_close_ts=min_close_ts,
            max_close_ts=max_close_ts, min_settled_ts=min_settled_ts, max_settled_ts=max_settled_ts,
        ))

    def get_market(self, ticker: str) -> dict[str, Any]:
        return self._get(f"/markets/{quote(ticker, safe='')}")

    def get_candlesticks(
        self, series_ticker: str, ticker: str, *, start_ts: int, end_ts: int, period_interval: int
    ) -> dict[str, Any]:
        path = f"/series/{quote(series_ticker, safe='')}/markets/{quote(ticker, safe='')}/candlesticks"
        return self._get(path, dict(start_ts=start_ts, end_ts=end_ts, period_interval=period_interval))

    def get_series(self, series_ticker: str) -> dict[str, Any]:
        """Returns {"series": {...}}; the series carries the fee type and fee multiplier of its markets."""
        return self._get(f"/series/{quote(series_ticker, safe='')}")

    # Events: one game or match with all its outcome markets.
    def list_events(
        self,
        *,
        series_ticker: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        with_nested_markets: bool | None = None,
    ) -> dict[str, Any]:
        nested = None if with_nested_markets is None else ("true" if with_nested_markets else "false")
        return self._get("/events", dict(
            series_ticker=series_ticker, status=status, limit=limit, cursor=cursor, with_nested_markets=nested,
        ))

    def get_event(self, event_ticker: str) -> dict[str, Any]:
        """Returns {"event": ..., "markets": [...]}. Without with_nested_markets Kalshi puts the markets at the top level."""
        return self._get(f"/events/{quote(event_ticker, safe='')}")

    # Milestones carry the real start time of a game (a market's occurrence time is the expected
    # settlement time instead). Kalshi requires `limit`.
    def list_series(self, *, category: str | None = None) -> dict[str, Any]:
        """Returns {"series": [...]}: each series has its tags (the sport), title, fee type and multiplier."""
        return self._get("/series", dict(category=category))

    def list_milestones(
        self,
        *,
        limit: int,
        category: str | None = None,
        minimum_start_date: str | None = None,
        related_event_ticker: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._get("/milestones", dict(
            limit=limit, category=category, minimum_start_date=minimum_start_date,
            related_event_ticker=related_event_ticker, cursor=cursor,
        ))

    # Markets that settled before Kalshi's "historical cutoff" are only served here.
    def get_historical_cutoff(self) -> dict[str, Any]:
        return self._get("/historical/cutoff")

    def list_historical_markets(self, *, limit: int | None = None, cursor: str | None = None, series_ticker: str | None = None) -> dict[str, Any]:
        return self._get("/historical/markets", dict(limit=limit, cursor=cursor, series_ticker=series_ticker))

    def get_historical_candlesticks(
        self, ticker: str, *, start_ts: int, end_ts: int, period_interval: int
    ) -> dict[str, Any]:
        path = f"/historical/markets/{quote(ticker, safe='')}/candlesticks"
        return self._get(path, dict(start_ts=start_ts, end_ts=end_ts, period_interval=period_interval))
