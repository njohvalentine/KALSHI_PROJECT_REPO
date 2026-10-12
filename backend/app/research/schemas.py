"""Data shapes shared by the research code."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class MarketInfo:
    ticker: str
    title: str
    subtitle: str | None = None
    close_time: str | None = None
    rules: str | None = None
    price_dollars: str | None = None  # kept for later steps; researchers are not shown it (avoids anchoring)

    @classmethod
    def from_kalshi(cls, data: dict) -> "MarketInfo":
        """Builds from Kalshi's market JSON. Field names follow Kalshi's docs and are unverified
        against a live response, so every field except the ticker is optional."""
        m = data.get("market", data)
        ticker = m.get("ticker")
        if not ticker:
            raise ValueError("Kalshi market data has no ticker")
        return cls(
            ticker=ticker,
            title=m.get("title") or ticker,
            subtitle=m.get("subtitle") or None,
            close_time=m.get("close_time") or None,
            rules=m.get("rules_primary") or None,
            price_dollars=m.get("last_price_dollars") or None,
        )


class Angle(BaseModel):
    name: str = Field(description="Short label for this line of research, a few words")
    question: str = Field(description="The specific question the researcher should answer by searching the web")


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
