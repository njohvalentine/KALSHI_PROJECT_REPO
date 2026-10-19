"""A price-only test on Kalshi's own history: is the price an hour before a game biased in a way that could be exploited after fees?

It reads Kalshi's public history (settled markets, milestones for the start times, hourly candles), takes a fixed sample of finished games,
and measures calibration, the Brier score and three simulated strategies. The rules (the sample, the price, the strategies, the halves and
the strict interval) were written in docs/specs/FEAT-20261017-1842-kalshi-price-test.md before any run. It reads only; it writes no database
row and places nothing. The prices are hourly bid and ask closes, not executable fills, so a pattern that passes is a reason for a live check."""

import hashlib
import json
import logging
import math
import random
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.kalshi import KalshiClient, KalshiError, KalshiNotFound
from app.research.compare import fee_info_from_series, fee_per_contract

log = logging.getLogger("app.research.pricetest")

SEED = 20261017
SAMPLE = 400  # games per series at most
MAX_SPREAD = Decimal("0.10")  # a game is kept only if every winner market has a spread of at most this
LONGSHOT = Decimal("0.20")
HOUR = 3600
RESAMPLES = 2000
SERIES = {  # series ticker -> (name, sector)
    "KXEPLGAME": ("Premier League", "Soccer"), "KXUCLGAME": ("Champions League", "Soccer"), "KXUELGAME": ("Europa League", "Soccer"),
    "KXMLSGAME": ("MLS", "Soccer"), "KXLALIGAGAME": ("La Liga", "Soccer"), "KXSERIEAGAME": ("Serie A", "Soccer"),
    "KXBUNDESLIGAGAME": ("Bundesliga", "Soccer"), "KXLIGUE1GAME": ("Ligue 1", "Soccer"),
    "KXMLBGAME": ("MLB", "Baseball"), "KXNBAGAME": ("NBA", "Basketball"),
    "KXATPMATCH": ("ATP", "Tennis"), "KXWTAMATCH": ("WTA", "Tennis"),
    "KXATPCHALLENGERMATCH": ("ATP Challenger", "Tennis"), "KXWTACHALLENGERMATCH": ("WTA Challenger", "Tennis"),
}
STRATEGIES = {
    "F": "buy yes on the favourite of each game",
    "L": "buy yes on every outcome priced at 20 cents or less",
    "N": "buy no on every outcome priced at 20 cents or less",
}


@dataclass
class Outcome:
    ticker: str
    bid: Decimal
    ask: Decimal
    won: bool

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


@dataclass
class Game:
    event: str
    series: str
    start: datetime
    outcomes: list[Outcome]


class Cache:
    """A folder of small JSON files, so a second run downloads nothing again."""

    def __init__(self, path: Path | None):
        self.path = path
        if path:
            path.mkdir(parents=True, exist_ok=True)

    def _file(self, name: str) -> Path:
        return self.path / (hashlib.sha1(name.encode()).hexdigest() + ".json")

    def get(self, name: str):
        if not self.path:
            return None
        file = self._file(name)
        return json.loads(file.read_text()) if file.exists() else None

    def put(self, name: str, value) -> None:
        if self.path:
            self._file(name).write_text(json.dumps(value))


def _num(candle_side: dict | None) -> Decimal | None:
    """The close of a bid or ask candle: the history tier calls the field `close`, the normal tier `close_dollars`."""
    if not candle_side:
        return None
    value = candle_side.get("close_dollars", candle_side.get("close"))
    return Decimal(str(value)) if value not in (None, "") else None


def pick_price(candles: list[dict], start_ts: int) -> tuple[Decimal, Decimal] | None:
    """(bid, ask) of the last candle that ends at least one hour before the start and has both, else None."""
    usable = [c for c in candles if c.get("end_period_ts") is not None and c["end_period_ts"] <= start_ts - HOUR]
    for candle in sorted(usable, key=lambda c: c["end_period_ts"], reverse=True):
        bid, ask = _num(candle.get("yes_bid")), _num(candle.get("yes_ask"))
        if bid is not None and ask is not None:
            return bid, ask
    return None


def _start_of(client: KalshiClient, event: str, cache: Cache) -> str | None:
    cached = cache.get(f"start-{event}")
    if cached is not None:
        return cached or None
    start = ""
    try:
        for m in client.list_milestones(limit=5, related_event_ticker=event).get("milestones", []):
            if event in (m.get("primary_event_tickers") or []) + (m.get("related_event_tickers") or []) and m.get("start_date"):
                start = m["start_date"]
                break
    except KalshiNotFound:
        pass
    cache.put(f"start-{event}", start)
    return start or None


def _candles_of(client: KalshiClient, ticker: str, start_ts: int, cache: Cache) -> list[dict]:
    cached = cache.get(f"candles-{ticker}")
    if cached is not None:
        return cached
    try:
        got = client.get_historical_candlesticks(ticker, start_ts=start_ts - 4 * HOUR, end_ts=start_ts - HOUR, period_interval=60).get("candlesticks", [])
    except KalshiNotFound:
        got = []
    cache.put(f"candles-{ticker}", got)
    return got


def _series_of(client: KalshiClient, series: str, cache: Cache) -> dict:
    cached = cache.get(f"series-{series}")
    if cached is not None:
        return cached
    got = client.get_series(series).get("series") or {}
    cache.put(f"series-{series}", got)
    return got


def _markets_of(client: KalshiClient, series: str, cache: Cache, log_line: Callable[[str], None]) -> list[dict]:
    cached = cache.get(f"markets-{series}")
    if cached is not None:
        return cached
    out, cursor = [], None
    while True:
        page = client.list_historical_markets(limit=1000, cursor=cursor, series_ticker=series)
        out += [{"ticker": m["ticker"], "event": m["event_ticker"], "result": m.get("result"), "close": m.get("close_time")} for m in page.get("markets", [])]
        cursor = page.get("cursor")
        log_line(f"{series}: {len(out)} markets listed")
        if not cursor or not page.get("markets"):
            break
    cache.put(f"markets-{series}", out)
    return out


def sample_events(markets: list[dict], sample: int = SAMPLE) -> tuple[list[str], Counter]:
    """The events of a series with a clear result, as every k-th one in order of settlement (at most `sample`); with the reasons for the others."""
    by_event: dict[str, list[dict]] = defaultdict(list)
    for m in markets:
        by_event[m["event"]].append(m)
    dropped, usable = Counter(), []
    for event, ms in by_event.items():
        results = [m["result"] or "" for m in ms]
        if len(ms) not in (2, 3):
            dropped["unusual market structure"] += 1
        elif sorted(results) != sorted(["yes"] + ["no"] * (len(ms) - 1)):
            dropped["no single winner (voided or unfinished)"] += 1
        else:
            usable.append((max(m["close"] or "" for m in ms), event))
    usable.sort()
    step = max(math.ceil(len(usable) / sample), 1) if usable else 1
    return [event for _, event in usable[::step][:sample]], dropped


def collect(client: KalshiClient, cache: Cache, series_list: list[str], sample: int = SAMPLE, workers: int = 6, pause: float = 0.05,
            log_line: Callable[[str], None] = lambda s: None) -> tuple[list[Game], Counter, dict]:
    """The sampled games with the price an hour before the start, the reasons games were dropped, and the fee of each series."""
    games, dropped, fees = [], Counter(), {}

    for series in series_list:
        fees[series] = fee_info_from_series(_series_of(client, series, cache))
        markets = _markets_of(client, series, cache, log_line)
        events, bad = sample_events(markets, sample)
        dropped.update({f"{series}: {k}": v for k, v in bad.items()})
        by_event = defaultdict(list)
        for m in markets:
            by_event[m["event"]].append(m)

        def one(event: str) -> Game | str:
            start_text = _start_of(client, event, cache)
            if not start_text:
                return "no start time"
            start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
            outcomes = []
            for m in by_event[event]:
                price = pick_price(_candles_of(client, m["ticker"], int(start.timestamp()), cache), int(start.timestamp()))
                time.sleep(pause)
                if price is None:
                    return "no bid and ask an hour before the start"
                bid, ask = price
                if not (0 < bid <= ask < 1):
                    return "no usable bid and ask (empty or crossed)"
                if ask - bid > MAX_SPREAD:
                    return "spread wider than 10 cents"
                outcomes.append(Outcome(m["ticker"], bid, ask, m["result"] == "yes"))
            return Game(event, series, start, outcomes)

        with ThreadPoolExecutor(workers) as pool:
            for done, result in enumerate(pool.map(one, events), 1):
                if isinstance(result, Game):
                    games.append(result)
                else:
                    dropped[f"{series}: {result}"] += 1
                if done % 50 == 0:
                    log_line(f"{series}: {done} of {len(events)} games read")
    return games, dropped, fees


# ---- the measurements ------------------------------------------------------------------------------------

def _fee(price: Decimal, fee) -> Decimal:
    return fee_per_contract(price, fee)


def game_results(game: Game, fee) -> dict[str, tuple[Decimal, int]]:
    """Per strategy: (the sum of the results of this game's bets, the number of bets); one contract each, at the ask, with the fee."""
    out = {"F": (Decimal(0), 0), "L": (Decimal(0), 0), "N": (Decimal(0), 0)}
    favourite = max(game.outcomes, key=lambda o: o.mid)
    for o in game.outcomes:
        yes_cost = o.ask + _fee(o.ask, fee)
        no_ask = 1 - o.bid
        no_cost = no_ask + _fee(no_ask, fee)
        yes_result = (Decimal(1) if o.won else Decimal(0)) - yes_cost
        no_result = (Decimal(0) if o.won else Decimal(1)) - no_cost
        if o is favourite:
            out["F"] = (out["F"][0] + yes_result, out["F"][1] + 1)
        if o.mid <= LONGSHOT:
            out["L"] = (out["L"][0] + yes_result, out["L"][1] + 1)
            out["N"] = (out["N"][0] + no_result, out["N"][1] + 1)
    return out


def bootstrap(per_game: list[tuple[Decimal, int]], seed: int = SEED, resamples: int = RESAMPLES) -> dict:
    """The average result per contract and its 95 and 99 percent intervals, by resampling WHOLE games (the outcomes of one game are not independent)."""
    games = [(float(s), n) for s, n in per_game if n > 0]
    if not games:
        return {"bets": 0, "mean": None, "ci95": None, "ci99": None}
    bets = sum(n for _, n in games)
    mean = sum(s for s, _ in games) / bets
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        pick = [games[rng.randrange(len(games))] for _ in games]
        total_bets = sum(n for _, n in pick)
        means.append(sum(s for s, _ in pick) / total_bets)
    means.sort()

    def interval(level: float) -> tuple[float, float]:
        lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
        return means[int(lo * (len(means) - 1))], means[int(hi * (len(means) - 1))]

    return {"bets": bets, "games": len(games), "mean": mean, "ci95": interval(0.95), "ci99": interval(0.99)}


def verdict(first: dict, second: dict) -> str:
    """The rule: found only if the second half is above zero with the lower end of its 99 percent interval above zero and the first half agrees in sign."""
    if second["mean"] is None or first["mean"] is None:
        return "too few bets"
    if second["mean"] > 0 and second["ci99"][0] > 0 and first["mean"] > 0:
        return "FOUND"
    if first["mean"] > 0:
        return "not confirmed"
    return "no pattern"


def calibration(games: list[Game]) -> list[dict]:
    rows = defaultdict(lambda: [0, Decimal(0), 0])
    for g in games:
        for o in g.outcomes:
            b = min(int(o.mid * 10), 9)
            rows[b][0] += 1
            rows[b][1] += o.mid
            rows[b][2] += 1 if o.won else 0
    return [{"bucket": f"{b * 10}-{b * 10 + 10}¢", "n": n, "mean_price": float(total / n), "rate": won / n} for b, (n, total, won) in sorted(rows.items())]


def brier(games: list[Game]) -> float | None:
    values = [(float(o.mid) - (1 if o.won else 0)) ** 2 for g in games for o in g.outcomes]
    return sum(values) / len(values) if values else None


def analyse(games: list[Game], fees: dict) -> dict:
    """Per group (each series, each sector, all): the calibration, the Brier score, and per strategy the two halves and the verdict."""
    groups: dict[str, list[Game]] = {"All": list(games)}
    for g in games:
        name, sector = SERIES[g.series]
        groups.setdefault(name, []).append(g)
        groups.setdefault(f"{sector} (all)", []).append(g)
    out = {}
    for name, members in groups.items():
        members = sorted(members, key=lambda g: g.start)
        half = len(members) // 2
        halves = (members[:half], members[half:])
        strategies = {}
        for key in STRATEGIES:
            per_half = [bootstrap([game_results(g, fees[g.series])[key] for g in h]) for h in halves]
            strategies[key] = {"first": per_half[0], "second": per_half[1], "verdict": verdict(*per_half)}
        out[name] = {"games": len(members), "from": members[0].start.date().isoformat() if members else None,
                     "to": members[-1].start.date().isoformat() if members else None, "brier": brier(members),
                     "calibration": calibration(members), "strategies": strategies}
    return out


def _c(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:+.1f}¢"


def format_report(result: dict, dropped: Counter, collected: int) -> str:
    lines = ["# Kalshi price test: raw results", "",
             f"Games read: {collected}. Prices: hourly bid and ask closes an hour before the start, not executable fills. Rule and strategies: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md`.",
             "A pattern is FOUND only if the second half is above zero with the lower end of its 99% interval above zero and the first half is also above zero.", "",
             "## Strategies", ""]
    lines += [f"- **{k}**: {v}" for k, v in STRATEGIES.items()] + ["", "## Results by group", "",
              "| Group | Games | Strategy | First half: bets, average | Second half: bets, average, 99% interval | Verdict |", "|---|---|---|---|---|---|"]
    for name, g in result.items():
        for k, s in g["strategies"].items():
            f, t = s["first"], s["second"]
            ci = "–" if t["ci99"] is None else f"{_c(t['ci99'][0])} to {_c(t['ci99'][1])}"
            lines.append(f"| {name} | {g['games']} | {k} | {f['bets']}, {_c(f['mean'])} | {t['bets']}, {_c(t['mean'])}, {ci} | {s['verdict']} |")
    lines += ["", "## Accuracy and calibration", "", "| Group | Games | Period | Brier score of the middle price |", "|---|---|---|---|"]
    lines += [f"| {n} | {g['games']} | {g['from']} to {g['to']} | {'–' if g['brier'] is None else f'{g['brier']:.4f}'} |" for n, g in result.items()]
    lines += ["", "### Calibration, all games", "", "| Price bucket | Outcomes | Mean price | How often it happened |", "|---|---|---|---|"]
    lines += [f"| {r['bucket']} | {r['n']} | {r['mean_price']:.3f} | {r['rate']:.3f} |" for r in result["All"]["calibration"]] if "All" in result else []
    lines += ["", "## Games dropped, and why", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(dropped.items())] or ["- none"]
    return "\n".join(lines) + "\n"


def run(client: KalshiClient, cache_dir: Path | None, series_list: list[str] | None = None, sample: int = SAMPLE, workers: int = 6,
        log_line: Callable[[str], None] = print) -> str:
    try:
        games, dropped, fees = collect(client, Cache(cache_dir), series_list or list(SERIES), sample, workers, log_line=log_line)
    except KalshiError as exc:
        raise SystemExit(f"Error: Kalshi could not be read ({exc}). Is the VPN on?") from None
    if not games:
        raise SystemExit("Error: no game could be used; see the reasons: " + str(dict(dropped)))
    return format_report(analyse(games, fees), dropped, len(games))
