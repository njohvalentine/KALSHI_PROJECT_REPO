"""The early record of every forecast, and the scoring of those records once the games are over.

A record is made before the game with the market price at that moment, and is never edited except
for the three result fields. Only live forecasts are recorded, so no hindsight can get in. The score
command prints the numbers and how many games they rest on; it prints no verdict."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.kalshi import KalshiClient
from app.models import OutcomeRecord
from app.research.compare import FEE_RATE
from app.research.schemas import GameInfo

log = logging.getLogger("app.research.records")

FINAL_STATUSES = ("determined", "finalized", "settled")  # Kalshi market states in which `result` is known
BATCH = 100
UNKNOWN_START_WAIT = timedelta(hours=24)  # a record with no game start is looked up this long after it was made
MIN_GAMES = 30
MIN_GROUP_GAMES = 5  # a sport, league or evidence group with fewer games than this is printed with a warning


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def build_records(
    run_id: str, game: GameInfo, prediction: dict, comparison: dict, baseline: dict[str, float] | None, created_at: datetime,
    book: dict | None = None,
) -> list[OutcomeRecord]:
    """One record per outcome from a finished prediction and its comparison. No prediction, no records."""
    if "outcomes" not in prediction:
        log.info("Run %s has no prediction; nothing to record", run_id)
        return []
    start = _parse_time(game.starts_at)
    priced = {o["market_ticker"]: o for o in comparison.get("outcomes", [])}
    fee = comparison.get("fee") or {}
    why_no_market = comparison.get("unavailable")
    book = book or {"at": None, "by_ticker": {}, "note": "no bookmaker price was looked for"}
    records = []
    for o in prediction["outcomes"]:
        c = priced.get(o["market_ticker"])
        kind = o.get("kind", "winner")
        b = book["by_ticker"].get(o["market_ticker"])
        yes, no = (c or {}).get("yes"), (c or {}).get("no")
        records.append(OutcomeRecord(
            run_id=run_id, event_ticker=game.event_ticker, market_ticker=o["market_ticker"], outcome=o["outcome"], sport=game.sport, league=game.league,
            game_start=start, created_at=created_at, before_start=None if start is None else created_at < start,
            probability=_dec(o["probability"]), prob_min=_dec(o["min"]), prob_max=_dec(o["max"]),
            forecasters_valid=prediction["forecasters_valid"], evidence=prediction["evidence"],
            supported_claims=prediction["supported_claims"],
            baseline_probability=_dec(baseline.get(o["market_ticker"])) if baseline else None,
            yes_bid=_dec((c or {}).get("yes_bid")), yes_ask=_dec((c or {}).get("yes_ask")), no_ask=_dec((c or {}).get("no_ask")),
            yes_ask_size=_dec(yes["size"]) if yes else None,
            yes_bid_size=_dec(no["size"]) if no else None,  # contracts at the best YES bid are the ones at the NO ask
            priced_at=_parse_time(comparison.get("priced_at")),
            fee_type=((c or {}).get("fee") or fee).get("fee_type"), fee_multiplier=_dec(((c or {}).get("fee") or fee).get("multiplier")),
            fee_source=((c or {}).get("fee") or fee).get("source"), market_kind=o.get("kind", "winner"),
            side=(c or {}).get("side"), net_edge=_dec((c or {}).get("net_edge")), worst_case_edge=_dec((c or {}).get("worst_case_edge")),
            meaningful=bool((c or {}).get("meaningful")),
            book_probability=_dec(round(b["probability"], 4)) if b else None, book_pinnacle=_dec(round(b["pinnacle"], 4)) if b and b["pinnacle"] is not None else None,
            book_count=b["count"] if b else None, book_at=book.get("at") if b else None,
            book_note=None if b else ("bookmaker prices are only read for winner markets" if kind != "winner" else book.get("note")),
            reasons=c["reasons"] if c is not None else ([f"no market snapshot: {why_no_market}"] if why_no_market else ["no market snapshot"]),
        ))
    return records


def save_records(engine, records: list[OutcomeRecord]) -> int:
    with DbSession(engine) as db:
        db.add_all(records)
        db.commit()
    return len(records)


def resolve_records(engine, client: KalshiClient, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """Fills in the result of records whose game is over. The only update path: it touches the three result
    fields and nothing else. Safe to run again and again."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=settings.resolve_after_hours)
    counts = {"resolved": 0, "voided_or_other": 0, "still_open": 0, "not_found": 0}
    with DbSession(engine) as db:
        due = db.scalars(select(OutcomeRecord).where(
            OutcomeRecord.resolved_at.is_(None),
            or_(OutcomeRecord.game_start < cutoff,
                (OutcomeRecord.game_start.is_(None)) & (OutcomeRecord.created_at < now - UNKNOWN_START_WAIT)),
        )).all()
        by_ticker: dict[str, list[OutcomeRecord]] = {}
        for r in due:
            by_ticker.setdefault(r.market_ticker, []).append(r)
        tickers = list(by_ticker)
        for i in range(0, len(tickers), BATCH):
            batch = tickers[i:i + BATCH]
            markets = {m["ticker"]: m for m in client.list_markets(tickers=",".join(batch), limit=len(batch)).get("markets", [])}
            for ticker in batch:
                market = markets.get(ticker)
                if market is None:
                    counts["not_found"] += len(by_ticker[ticker])
                    continue
                if market.get("status") not in FINAL_STATUSES:
                    counts["still_open"] += len(by_ticker[ticker])
                    continue
                result = market.get("result")
                for r in by_ticker[ticker]:
                    r.resolved_at = now
                    r.settlement_value = _dec(market.get("settlement_value_dollars"))
                    if result in ("yes", "no"):
                        r.resolved_yes = result == "yes"
                        counts["resolved"] += 1
                    else:  # voided, or settled at another value: kept as it is, left out of the scores
                        r.resolved_yes = None
                        counts["voided_or_other"] += 1
            db.commit()  # batch by batch, so a Kalshi failure later does not lose what was learned
    from app.orders import settle_orders  # simulated orders whose game has ended are settled with the same results

    counts["orders_settled"] = settle_orders(engine, now)
    log.info("Resolved records: %s", counts)
    return counts


def _brier(pairs: list[tuple[Decimal, bool]]) -> float | None:
    return float(sum((p - (1 if y else 0)) ** 2 for p, y in pairs) / len(pairs)) if pairs else None


def _mid(r: OutcomeRecord) -> Decimal | None:
    """Middle of the YES bid and ask, only when both sides are quoted."""
    if r.yes_bid is None or r.yes_ask is None or not (0 < r.yes_bid <= r.yes_ask < 1):
        return None
    return (r.yes_bid + r.yes_ask) / 2


def _paper(records: list[OutcomeRecord]) -> dict:
    """What buying the chosen side at the ask would have paid per contract: win 1, minus price, minus taker fee."""
    results = []
    for r in records:
        price = r.yes_ask if r.side == "yes" else r.no_ask
        if r.side is None or price is None:
            continue
        multiplier = r.fee_multiplier if r.fee_multiplier is not None else Decimal(1)
        fee = FEE_RATE * multiplier * price * (1 - price)
        won = r.resolved_yes if r.side == "yes" else not r.resolved_yes
        results.append((won, (Decimal(1) if won else Decimal(0)) - price - fee))
    n = len(results)
    return {
        "bets": n,
        "won": sum(1 for w, _ in results if w),
        "average_result": float(sum(x for _, x in results) / n) if n else None,
        "total_result": float(sum(x for _, x in results)) if n else None,
    }


def _group_scores(used: list[OutcomeRecord], key) -> dict:
    """The same numbers per group (kind of market, sport, league, amount of evidence): the forecasts may be good for one group and poor for another."""
    out = {}
    for kind in sorted({key(r) for r in used}):
        rows = [r for r in used if key(r) == kind]
        both = [r for r in rows if r.baseline_probability is not None and _mid(r) is not None]
        out[kind] = {
            "outcomes": len(rows), "games": len({r.event_ticker for r in rows}),
            "brier_ours": _brier([(r.probability, r.resolved_yes) for r in rows]),
            "same_records": {
                "n": len(both),
                "ours": _brier([(r.probability, r.resolved_yes) for r in both]),
                "baseline": _brier([(r.baseline_probability, r.resolved_yes) for r in both]),
                "market": _brier([(_mid(r), r.resolved_yes) for r in both]),
            },
            "paper_all": _paper(rows),
            "paper_flagged": _paper([r for r in rows if r.meaningful]),  # how the flagged bets of this group did
        }
    return out


def _where(r: OutcomeRecord, series: dict[str, tuple[str, str]] | None) -> tuple[str, str]:
    """The sport and league of a record: its own columns, else the configured series of its game, else unknown."""
    if r.sport:
        return r.sport, r.league or r.sport
    return (series or {}).get(r.event_ticker.split("-")[0], ("unknown", "unknown"))


def _evidence_bucket(flag_claims: int):
    """none, a few, enough: the edge is the number of supported claims a flag needs (MIN_SUPPORTED_CLAIMS)."""
    def bucket(r: OutcomeRecord) -> str:
        if r.supported_claims == 0:
            return "none"
        return f"1 to {flag_claims - 1} supported claims" if r.supported_claims < flag_claims else f"{flag_claims} or more supported claims"
    return bucket


def score_records(engine, since: datetime | None = None, series: dict[str, tuple[str, str]] | None = None, flag_claims: int = 5) -> dict:
    """A record has its own sport and league (set when it was made). `series` maps a series ticker to (sport, league), from
    SPORTS_SERIES, for records made before those columns existed and without a backfill; otherwise they are "unknown"."""
    with DbSession(engine) as db:
        query = select(OutcomeRecord)
        if since:
            query = query.where(OutcomeRecord.created_at >= since)
        records = db.scalars(query).all()
    unresolved = [r for r in records if r.resolved_at is None]
    voided = [r for r in records if r.resolved_at is not None and r.resolved_yes is None]
    scored_pool = [r for r in records if r.resolved_yes is not None]
    late = [r for r in scored_pool if r.before_start is not True]  # made after the start, or start unknown
    before = [r for r in scored_pool if r.before_start is True]
    # A market can have several forecasts (the game was researched again). The headline uses the latest one made
    # before the start, the most informed; the first one is kept to show whether updating helped.
    by_market: dict[str, list[OutcomeRecord]] = {}
    for r in before:
        by_market.setdefault(r.market_ticker, []).append(r)
    used = [max(group, key=lambda r: (r.created_at, r.id)) for group in by_market.values()]
    updated = {t: g for t, g in by_market.items() if len(g) > 1}
    first = [min(g, key=lambda r: (r.created_at, r.id)) for g in updated.values()]
    latest_of_updated = [max(g, key=lambda r: (r.created_at, r.id)) for g in updated.values()]

    ours = [(r.probability, r.resolved_yes) for r in used]
    with_all = [r for r in used if r.baseline_probability is not None and _mid(r) is not None]
    winners = [r for r in used if r.market_kind == "winner"]
    with_book = [r for r in with_all if r.book_probability is not None]
    with_pinnacle = [r for r in with_book if r.book_pinnacle is not None]
    return {
        "records": len(records), "used": len(used), "games": len({r.event_ticker for r in used}),
        "updated": {
            "markets": len(updated),
            "brier_first": _brier([(r.probability, r.resolved_yes) for r in first]),
            "brier_latest": _brier([(r.probability, r.resolved_yes) for r in latest_of_updated]),
        },
        "excluded": {"unresolved": len(unresolved), "voided_or_other": len(voided), "after_start_or_unknown": len(late)},
        "brier_ours": _brier(ours),
        "same_records": {
            "n": len(with_all),
            "ours": _brier([(r.probability, r.resolved_yes) for r in with_all]),
            "baseline": _brier([(r.baseline_probability, r.resolved_yes) for r in with_all]),
            "market": _brier([(_mid(r), r.resolved_yes) for r in with_all]),
        },
        "bookmakers": {
            "winner_outcomes": len(winners), "winner_games": len({r.event_ticker for r in winners}),
            "covered_outcomes": sum(1 for r in winners if r.book_probability is not None),
            "covered_games": len({r.event_ticker for r in winners if r.book_probability is not None}),
            "n": len(with_book), "games": len({r.event_ticker for r in with_book}),
            "ours": _brier([(r.probability, r.resolved_yes) for r in with_book]),
            "baseline": _brier([(r.baseline_probability, r.resolved_yes) for r in with_book]),
            "market": _brier([(_mid(r), r.resolved_yes) for r in with_book]),
            "book": _brier([(r.book_probability, r.resolved_yes) for r in with_book]),
            "pinnacle_n": len(with_pinnacle),
            "pinnacle": _brier([(r.book_pinnacle, r.resolved_yes) for r in with_pinnacle]),
            "pinnacle_ours": _brier([(r.probability, r.resolved_yes) for r in with_pinnacle]),
        },
        "without_two_sided_quote": sum(1 for r in used if _mid(r) is None),
        "without_baseline": sum(1 for r in used if r.baseline_probability is None),
        "by_kind": _group_scores(used, lambda r: r.market_kind),
        "by_sport": _group_scores(used, lambda r: _where(r, series)[0]),
        "by_league": _group_scores(used, lambda r: _where(r, series)[1]),
        "by_evidence": _group_scores(used, _evidence_bucket(flag_claims)),
        "paper_all": _paper(used),
        "paper_flagged": _paper([r for r in used if r.meaningful]),
        "enough_games": len({r.event_ticker for r in used}) >= MIN_GAMES,
    }


def format_report(s: dict) -> str:
    def f(x):
        return "n/a" if x is None else f"{x:.4f}"

    lines = [
        f"Records: {s['records']}; scored: {s['used']} outcomes in {s['games']} games (the latest forecast made before the start for each market).",
        "Left out: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in s["excluded"].items()) + ".",
        f"Brier score of our probability (lower is better), all scored outcomes: {f(s['brier_ours'])}",
        f"On the {s['same_records']['n']} outcomes that have all three: ours {f(s['same_records']['ours'])}, "
        f"plain AI call {f(s['same_records']['baseline'])}, Kalshi price (bid-ask middle) {f(s['same_records']['market'])}",
        f"Not in that comparison: {s['without_two_sided_quote']} without a two-sided quote, {s['without_baseline']} without a baseline.",
    ]
    bk = s.get("bookmakers")
    if bk and bk["covered_outcomes"]:
        lines.append(
            f"Bookmakers (winner markets only): {bk['covered_outcomes']} of {bk['winner_outcomes']} scored winner outcomes ({bk['covered_games']} of {bk['winner_games']} games) have a bookmaker price. "
            f"On the {bk['n']} that also have the other three: ours {f(bk['ours'])}, plain AI {f(bk['baseline'])}, Kalshi {f(bk['market'])}, bookmaker consensus {f(bk['book'])}."
        )
        if bk["pinnacle_n"]:
            lines.append(f"  Pinnacle alone, on the {bk['pinnacle_n']} that have it: Pinnacle {f(bk['pinnacle'])} against ours {f(bk['pinnacle_ours'])}.")
    elif bk:
        lines.append("Bookmakers: no scored outcome has a bookmaker price yet (the benchmark records only forecasts made while it is on, for winner markets in the leagues the feed lists).")
    for heading, groups in (("By kind of market", s.get("by_kind")), ("By sport", s.get("by_sport")), ("By league", s.get("by_league")),
                            ("By amount of confirmed evidence", s.get("by_evidence"))):
        if not groups:
            continue
        lines.append(f"{heading}:")
        for kind, k in groups.items():
            same = k["same_records"]
            lines.append(
                f"  {kind}: {k['outcomes']} outcomes in {k['games']} games, Brier ours {f(k['brier_ours'])}; on the {same['n']} with all three: "
                f"ours {f(same['ours'])}, plain AI {f(same['baseline'])}, Kalshi {f(same['market'])}; chosen side at the ask: "
                f"{k['paper_all']['bets']} bets, average {f(k['paper_all']['average_result'])} dollars"
                + (f" (too few games: fewer than {MIN_GROUP_GAMES})" if k["games"] < MIN_GROUP_GAMES else "")
            )
    for key, label in (("paper_all", "Chosen side at the ask, all"), ("paper_flagged", "Chosen side at the ask, flagged as meaningful")):
        p = s[key]
        lines.append(
            f"{label}: {p['bets']} bets, {p['won']} won, average result per contract {f(p['average_result'])} dollars, total {f(p['total_result'])}"
        )
    if s.get("updated", {}).get("markets"):
        u = s["updated"]
        lines.append(
            f"{u['markets']} markets were forecast more than once: Brier of the first forecast {f(u['brier_first'])}, of the latest {f(u['brier_latest'])} "
            "(lower is better; a few markets prove nothing)."
        )
    if not s["enough_games"]:
        lines.append(f"Fewer than {MIN_GAMES} games: too few to conclude anything.")
    return "\n".join(lines)
