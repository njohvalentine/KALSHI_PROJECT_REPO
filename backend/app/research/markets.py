"""Finds the other Kalshi markets of a game (total goals or runs, both teams to score, spread).

Kalshi lists them as separate events whose ticker shares the game's date-and-teams suffix:
KXUCLGAME-26OCT13ATMMUN (winner) goes with KXUCLTOTAL-26OCT13ATMMUN, KXUCLBTTS-..., KXUCLSPREAD-...
(read live on 2026-10-13 for the Premier League, the Champions League and MLB). A companion that
does not exist is simply not offered: it is noted, never guessed."""

import logging

from app.kalshi import KalshiClient, KalshiError, KalshiNotFound
from app.research.schemas import GameInfo, MarketGroup

log = logging.getLogger("app.research.markets")

# (kind, ticker part) per sport. More kinds (corners, team totals, tennis) are added here. A kind name is at most 10 characters (runs.market_kind).
COMPANIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "Soccer": (("total", "TOTAL"), ("btts", "BTTS"), ("spread", "SPREAD"),
               ("h1_winner", "1H"), ("h1_total", "1HTOTAL"), ("h1_btts", "1HBTTS"), ("h1_spread", "1HSPREAD")),  # first half, read live for the Premier League 2026-10-23
    "Baseball": (("total", "TOTAL"), ("spread", "SPREAD")),
    "Basketball": (("total", "TOTAL"), ("spread", "SPREAD")),  # NBA read live 2026-10-15; other leagues are tried by the same rule
}
KIND_NAMES = {"total": "total goals, runs or points", "btts": "both teams to score", "spread": "margin of victory",
              "h1_winner": "first half winner", "h1_total": "first half total goals", "h1_btts": "first half both teams to score",
              "h1_spread": "first half margin of victory"}
TEAM_KINDS = ("spread", "h1_winner", "h1_spread")  # the markets whose text starts with the team they are about
OPEN = (None, "active", "open")


def companion_ticker(winner_event: dict, part: str) -> str | None:
    """KXUCLGAME-26OCT13ATMMUN with part TOTAL gives KXUCLTOTAL-26OCT13ATMMUN."""
    series, event = winner_event.get("series_ticker") or "", winner_event.get("event_ticker") or ""
    if not series.endswith("GAME") or "-" not in event:
        return None
    return f"{series[:-4]}{part}-{event.split('-', 1)[1]}"


def _team_of(market: dict, names: list[str]) -> str | None:
    """The winner outcome a spread market is about: its text starts with that outcome's short name."""
    text = market.get("yes_sub_title") or market.get("title") or ""
    return next((n for n in names if n and n.lower() != "tie" and text.lower().startswith(n.lower())), None)


def group_from_event(kind: str, data: dict, names: list[str]) -> MarketGroup | None:
    event = data.get("event") or {}
    markets = [m for m in (data.get("markets") or event.get("markets") or []) if m.get("status") in OPEN]
    if not markets:
        return None
    team = (lambda m: _team_of(m, names)) if kind in TEAM_KINDS else (lambda m: None)
    markets.sort(key=lambda m: (team(m) or "" if kind in ("spread", "h1_spread") else "", m.get("floor_strike") is None, m.get("floor_strike") or 0))  # the first-half winner keeps Kalshi's order
    return MarketGroup(
        kind=kind, title=event.get("title") or kind, event_ticker=event.get("event_ticker") or "",
        series_ticker=event.get("series_ticker"), tickers=[m["ticker"] for m in markets],
        outcomes=[m.get("yes_sub_title") or m.get("title") or m["ticker"] for m in markets],
        strikes=[m.get("floor_strike") for m in markets],
        teams=[team(m) for m in markets],
    )


def attach_companions(game: GameInfo, winner_data: dict, sport: str | None, kalshi: KalshiClient) -> GameInfo:
    """Returns the game with the companion markets that exist, and a note for each that does not."""
    kinds = COMPANIONS.get(sport or "", ())
    if not kinds:
        return game
    event = winner_data.get("event") or {}
    groups, notes = [], []
    for kind, part in kinds:
        ticker = companion_ticker(event, part)
        label = KIND_NAMES[kind]
        if ticker is None:
            notes.append(f"{label}: the game's ticker does not allow looking for it")
            continue
        try:
            group = group_from_event(kind, kalshi.get_event(ticker), game.outcome_names)
        except KalshiNotFound:
            notes.append(f"{label}: not offered for this game")
            continue
        except KalshiError as exc:
            log.warning("Companion market %s could not be read: %s", ticker, exc)
            notes.append(f"{label}: could not be read from Kalshi")
            continue
        if group is None:
            notes.append(f"{label}: no open markets")
        else:
            groups.append(group)
    return GameInfo(**(game.__dict__ | {"groups": groups, "group_notes": notes}))
