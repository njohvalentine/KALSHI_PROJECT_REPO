"""Data shapes shared by the research code."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class GameInfo:
    """The game (a Kalshi event) a run is about, with the outcomes people can bet on."""

    event_ticker: str
    title: str
    sub_title: str | None = None
    starts_at: str | None = None
    outcomes: list[str] = field(default_factory=list)  # e.g. ["Newcastle wins", "Tie is the result", ...]
    outcome_tickers: list[str] = field(default_factory=list)  # the Kalshi market of each outcome, same order
    exclusive: bool = False  # Kalshi says at most one outcome happens (mutually_exclusive)
    rules: str | None = None
    # Prices are deliberately not part of what the agents are shown (avoids anchoring on the market).

    @property
    def sums_to_one(self) -> bool:
        """True when the outcome probabilities must add up to 100%: exactly one outcome happens. Kalshi's flag
        only says at most one does, so we also need the outcomes to cover every result. Checked live on
        2026-10-13 for all 15 configured series: soccer winner events have three outcomes (home, away, Tie),
        baseball and tennis two. Anything else (for example a futures market) is not scaled."""
        n = len(self.outcomes)
        return self.exclusive and (n == 2 or (n == 3 and any(w in o.lower() for o in self.outcomes for w in ("tie", "draw"))))

    @classmethod
    def from_kalshi_event(cls, data: dict, starts_at: str | None = None) -> "GameInfo":
        """Builds from Kalshi's GET /events/{ticker} response: {"event": {...}, "markets": [...]}.

        `starts_at` is the real kickoff from Kalshi's milestones. The markets' occurrence_datetime is
        NOT used: it is the expected settlement time (hours after kickoff), so it would be wrong."""
        event = data.get("event") or {}
        ticker = event.get("event_ticker")
        markets = data.get("markets") or event.get("markets") or []
        if not ticker or not markets:
            raise ValueError("Kalshi event data has no ticker or no outcome markets")
        return cls(
            event_ticker=ticker,
            title=event.get("title") or ticker,
            sub_title=event.get("sub_title") or None,
            starts_at=starts_at,
            outcomes=[m.get("title") or m.get("yes_sub_title") or m["ticker"] for m in markets],
            outcome_tickers=[m["ticker"] for m in markets],
            exclusive=bool(event.get("mutually_exclusive")),
            rules=next((m["rules_primary"] for m in markets if m.get("rules_primary")), None),
        )


class Angle(BaseModel):
    name: str = Field(description="Short label for this line of research, a few words")
    question: str = Field(description="The specific question the researcher should answer by searching the web")
    kind: Literal["evidence", "market_odds"] = Field(
        default="evidence",
        description="market_odds for the angle about bookmaker odds or market prices, evidence for every other angle",
    )


def is_market_angle(kind: str | None, name: str | None) -> bool:
    """True for findings about odds or market prices. Those are market information: the forecasters must not
    see them. The planner sets the kind; a name containing "odds" counts too, in case it mislabels."""
    return kind == "market_odds" or "odds" in (name or "").lower()


class Plan(BaseModel):
    angles: list[Angle]


@dataclass(frozen=True)
class Citation:
    url: str
    title: str
    start: int
    end: int


@dataclass(frozen=True)
class TextSegment:
    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0


@dataclass(frozen=True)
class ResearchOutput:
    segments: list[TextSegment]
    usage: Usage
