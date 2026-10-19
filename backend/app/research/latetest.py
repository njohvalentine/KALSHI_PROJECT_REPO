"""A free test of the last minutes of a market: buy NO on 10 to 40 cent contracts shortly before the close, at the real ask with the fee.

The rule (the entry minute, the price band, the filters, the halves, the strict interval) was written in
docs/specs/FEAT-20261019-1231-late-game-price-test.md before any run. It uses the market's real close time, which a trader in the game cannot know,
so a pass is NOT a tradable strategy; it only decides whether a tradable version is worth a second spec. It reads only; it writes no database row."""

import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.kalshi import KalshiClient, KalshiError, KalshiNotFound
from app.research.compare import fee_info_from_series, fee_per_contract
from app.research.pricetest import (MAX_SPREAD, SAMPLE, SERIES, Cache, _markets_of, _num, _series_of, _start_of, bootstrap, patient, sample_events, verdict)

ENTRY = 300  # seconds before the close: the tested entry; 600 and 120 are shown as descriptive rows
ENTRIES = (ENTRY, 600, 120)
BAND = (Decimal("0.10"), Decimal("0.40"))  # YES middle price
MIN_VOLUME = Decimal(10)  # contracts traded in the 5 minutes before the entry candle (depth is not in the history)
MIN_BETS = 100  # in each half, or the verdict is "too few bets"
WINDOW = 1800  # seconds of minute candles read before the close
FIXED_CLOSE_MINUTES = 5  # a series whose close minus start varies by less than this (median absolute deviation) has a fixed close, not the real end


@dataclass
class LateGame:
    event: str
    series: str
    start: datetime
    bets: dict[int, list[tuple[Decimal, bool]]]  # entry seconds -> (result of one contract, quote unchanged for the 5 minutes before)


def _ts(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def _both(candle: dict) -> tuple[Decimal, Decimal] | None:
    bid, ask = _num(candle.get("yes_bid")), _num(candle.get("yes_ask"))
    return (bid, ask) if bid is not None and ask is not None else None


def late_bets(candles: list[dict], close_ts: int, won: bool, fee, entry: int = ENTRY, dropped: Counter | None = None) -> list[tuple[Decimal, bool]]:
    """The bet this market gives at `entry` seconds before the close: [] or [(result, stale)]. `dropped` counts the reasons an in-band price was not used."""
    drop = dropped if dropped is not None else Counter()
    usable = sorted((c for c in candles if c.get("end_period_ts") is not None and c["end_period_ts"] <= close_ts - entry and _both(c)), key=lambda c: c["end_period_ts"])
    if not usable:
        drop["no bid and ask before the entry"] += 1
        return []
    at = usable[-1]
    bid, ask = _both(at)
    if not (0 < bid <= ask < 1) or not (BAND[0] <= (bid + ask) / 2 <= BAND[1]):
        return []  # out of the band: not a bet, not a drop
    if ask - bid > MAX_SPREAD:
        drop["spread wider than 10 cents"] += 1
        return []
    recent = [c for c in candles if c.get("end_period_ts") is not None and at["end_period_ts"] - ENTRY < c["end_period_ts"] <= at["end_period_ts"]]
    if sum(Decimal(str(c.get("volume") or 0)) for c in recent) < MIN_VOLUME:
        drop["fewer than 10 contracts traded in the 5 minutes before"] += 1
        return []
    stale = all(_both(c) == (bid, ask) for c in recent)
    no_ask = 1 - bid
    return [((Decimal(0) if won else Decimal(1)) - no_ask - fee_per_contract(no_ask, fee), stale)]


def fixed_close(starts_and_closes: list[tuple[int, int]]) -> bool:
    """True when close minus start hardly varies (soccer: always start + 120 minutes), so the 'last minutes' would be a fixed clock time."""
    gaps = [(c - s) / 60 for s, c in starts_and_closes]
    if len(gaps) < 2:
        return False
    median = statistics.median(gaps)
    return statistics.median(abs(g - median) for g in gaps) < FIXED_CLOSE_MINUTES


def collect(client: KalshiClient, cache: Cache, series_list: list[str], sample: int = SAMPLE, workers: int = 3, pause: float = 0.1,
            log_line: Callable[[str], None] = lambda s: None) -> tuple[list[LateGame], Counter, list[str]]:
    games, dropped, excluded = [], Counter(), []
    for series in series_list:
        fee = fee_info_from_series(_series_of(client, series, cache))
        markets = _markets_of(client, series, cache, log_line)
        events, bad = sample_events(markets, sample)
        dropped.update({f"{series}: {k}": v for k, v in bad.items()})
        by_event = defaultdict(list)
        for m in markets:
            by_event[m["event"]].append(m)

        def start_of(event: str) -> str | None:
            try:
                return _start_of(client, event, cache)
            except KalshiError:
                return None

        with ThreadPoolExecutor(workers) as pool:
            starts = dict(zip(events, pool.map(start_of, events), strict=True))
        pairs = [(_ts(starts[e]), _ts(by_event[e][0]["close"])) for e in events if starts[e] and by_event[e][0]["close"]]
        if fixed_close(pairs):
            excluded.append(series)
            continue

        def one(event: str) -> tuple[LateGame | str, Counter]:
            drops = Counter()  # per game, merged below: the workers never share a counter
            if not starts[event]:
                return "no start time", drops
            bets: dict[int, list] = {e: [] for e in ENTRIES}
            for m in by_event[event]:
                if not m["close"]:
                    return "no close time", drops
                close_ts = _ts(m["close"])
                key = f"late-candles-{m['ticker']}"
                candles = cache.get(key)
                if candles is None:
                    try:
                        candles = patient(lambda: client.get_historical_candlesticks(m["ticker"], start_ts=close_ts - WINDOW, end_ts=close_ts, period_interval=1)).get("candlesticks", [])
                    except KalshiNotFound:
                        candles = []
                    except KalshiError:
                        return "Kalshi could not be read after repeated tries", drops
                    cache.put(key, candles)
                    time.sleep(pause)
                for entry in ENTRIES:
                    bets[entry] += late_bets(candles, close_ts, m["result"] == "yes", fee, entry, drops if entry == ENTRY else None)
            return LateGame(event, series, datetime.fromisoformat(starts[event].replace("Z", "+00:00")), bets), drops

        with ThreadPoolExecutor(workers) as pool:
            for done, (result, drops) in enumerate(pool.map(one, events), 1):
                dropped.update(drops)
                if isinstance(result, LateGame):
                    games.append(result)
                else:
                    dropped[f"{series}: {result}"] += 1
                if done % 50 == 0:
                    log_line(f"{series}: {done} of {len(events)} games read")
    return games, dropped, excluded


def late_verdict(first: dict, second: dict) -> str:
    if first["bets"] < MIN_BETS or second["bets"] < MIN_BETS:
        return "too few bets"
    return verdict(first, second)


def analyse(games: list[LateGame]) -> dict:
    groups: dict[str, list[LateGame]] = {"All": list(games)}
    for g in games:
        groups.setdefault(f"{SERIES[g.series][1]} (all)", []).append(g)
    out = {}
    for name, members in groups.items():
        members = sorted(members, key=lambda g: g.start)
        half = len(members) // 2
        rows = {}
        for entry in ENTRIES:
            per_half = [bootstrap([(sum((r for r, _ in g.bets[entry]), Decimal(0)), len(g.bets[entry])) for g in h]) for h in (members[:half], members[half:])]
            all_bets = [b for g in members for b in g.bets[entry]]
            rows[entry] = {"first": per_half[0], "second": per_half[1], "stale": sum(1 for _, s in all_bets if s), "bets": len(all_bets),
                           "verdict": late_verdict(*per_half) if entry == ENTRY else "descriptive"}
        out[name] = {"games": len(members), "from": members[0].start.date().isoformat() if members else None, "to": members[-1].start.date().isoformat() if members else None, "rows": rows}
    return out


def _c(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:+.1f}¢"


def format_report(result: dict, dropped: Counter, collected: int, excluded: list[str]) -> str:
    lines = ["# Kalshi late-game test: raw results", "",
             f"Games read: {collected}. Bet: one contract of NO on every outcome whose YES middle price is 10 to 40 cents, at the NO ask plus the series fee, held to the result. "
             "Rule: `docs/specs/FEAT-20261019-1231-late-game-price-test.md`. The tested entry is 5 minutes before the close; 10 and 2 minutes are descriptive.",
             "**The close time is the real end of the game, known only afterwards, so this is NOT a tradable strategy.** No depth data; minute bid and ask closes are not fills.",
             "A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero, the first half is also above zero, and each half has at least 100 bets.", "",
             f"Series left out because their close is a fixed time after the start, not the real end: {', '.join(excluded) or 'none'}.", "",
             "| Group | Games | Entry | First half: bets, average | Second half: bets, average, 99% interval | Quote unchanged 5 min before (all bets) | Verdict |", "|---|---|---|---|---|---|---|"]
    for name, g in result.items():
        for entry, r in g["rows"].items():
            f, t = r["first"], r["second"]
            ci = "–" if t["ci99"] is None else f"{_c(t['ci99'][0])} to {_c(t['ci99'][1])}"
            lines.append(f"| {name} | {g['games']} | {entry // 60} min | {f['bets']}, {_c(f['mean'])} | {t['bets']}, {_c(t['mean'])}, {ci} | {r['stale']} of {r['bets']} | {r['verdict']} |")
    lines += ["", "## Bets not used, and why (5-minute entry, in-band prices only)", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(dropped.items())] or ["- none"]
    return "\n".join(lines) + "\n"


def run(client: KalshiClient, cache_dir: Path | None, series_list: list[str] | None = None, sample: int = SAMPLE, workers: int = 3,
        log_line: Callable[[str], None] = print) -> str:
    try:
        games, dropped, excluded = collect(client, Cache(cache_dir), series_list or list(SERIES), sample, workers, log_line=log_line)
    except KalshiError as exc:
        raise SystemExit(f"Error: Kalshi could not be read ({exc}). Is the VPN on?") from None
    if not games:
        raise SystemExit("Error: no game could be used; left out as fixed-close: " + ", ".join(excluded) + "; reasons: " + str(dict(dropped)))
    return format_report(analyse(games), dropped, len(games), excluded)
