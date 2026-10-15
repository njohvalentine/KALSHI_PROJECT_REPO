"""Which sports and games Kalshi offers, found from Kalshi itself instead of a fixed list of leagues.

Kalshi lists 3,978 sports series, far too many to ask one by one (read 2026-10-15). Two cheap sources are combined:
the series list (once a day: each series has tags, which name the sport, a title and a fee) and the milestones that
the Games page already reads for kickoff times (each is a game or match with its main event ticker and a type).
A game is a milestone whose main events include the winner event of a series with a sport tag and a title that ends in
Game, Match or Fight ("NBA Game", "ATP Match"). The milestone's own type is not used: Kalshi types every soccer match
soccer_tournament_multi_leg (read live 2026-10-15), and its main events list the spread, total and both-teams-to-score
events of the match as well, which are not games and are skipped because their series titles do not end that way.
Tournaments and futures are left out for the same reason. Nothing is guessed: a series that is not in the list is skipped."""

import logging
import threading
import time
from collections.abc import Callable

from app.config import SeriesEntry
from app.kalshi import KalshiClient

log = logging.getLogger("app.discovery")

SERIES_CACHE_SECONDS = 24 * 3600
GAME_TITLE_TAILS = (" Game", " Match", " Fight")  # the series of single games: "NBA Game", "ATP Challenger Match"
MAX_DISCOVERED_SERIES = 60  # series loaded at once for one sport; the busiest first, the rest noted


def is_game_series(title: str) -> bool:
    return title.endswith(GAME_TITLE_TAILS)


def league_of(title: str) -> str:
    """'NBA Game' gives 'NBA', 'ATP Challenger Match' gives 'ATP Challenger'."""
    for tail in GAME_TITLE_TAILS:
        if title.endswith(tail):
            return title[: -len(tail)]
    return title


class SeriesCatalog:
    """Series with a sport tag, from Kalshi, kept for a day. Series with an excluded tag are left out."""

    def __init__(self, get_kalshi: Callable[[], KalshiClient], exclude_tags: tuple[str, ...], clock: Callable[[], float] = time.monotonic):
        self._get_kalshi, self._exclude, self._clock = get_kalshi, {t.lower() for t in exclude_tags}, clock
        self._lock = threading.Lock()
        self._cache: tuple[float, dict[str, SeriesEntry]] | None = None

    def entries(self) -> dict[str, SeriesEntry]:
        with self._lock:
            if self._cache and self._clock() < self._cache[0]:
                return self._cache[1]
            series = self._get_kalshi().list_series(category="Sports").get("series", [])
            found: dict[str, SeriesEntry] = {}
            for s in series:
                tags = s.get("tags") or []
                if not tags or any(t.lower() in self._exclude for t in tags) or not is_game_series(s.get("title") or ""):
                    continue
                found[s["ticker"]] = SeriesEntry(sport=tags[0], ticker=s["ticker"], league=league_of(s.get("title") or s["ticker"]))
            log.info("Sports catalog: %d series with a sport tag (of %d read).", len(found), len(series))
            self._cache = (self._clock() + SERIES_CACHE_SECONDS, found)
            return found

    def entry_of(self, series_ticker: str | None) -> SeriesEntry | None:
        return self.entries().get(series_ticker or "")


def upcoming_series(milestones: list[dict], since_iso: str) -> dict[str, int]:
    """Number of milestones per series (from the tickers of their main events) that start at or after `since_iso`. Series that
    are not games (spread, total, ...) are counted here too; the caller keeps only the series of the catalog."""
    counts: dict[str, int] = {}
    for m in milestones:
        if (m.get("start_date") or "") < since_iso:
            continue
        for series in {t.split("-")[0] for t in m.get("primary_event_tickers") or []}:
            counts[series] = counts.get(series, 0) + 1
    return counts
