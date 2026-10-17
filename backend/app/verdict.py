"""NO BET, or worth a look: the one answer about a game that the Opportunities page, the run page and the alerts all give.

The rule lives here only, so the three cannot disagree. The answer is never "bet": at best it is "worth a look", and it
carries a caution while the finished games do not show that our forecasts beat the Kalshi price, or while the sport has no
scored results (the flag has not been tested there)."""

import time

from app.config import Settings
from app.dashboard import verdict as track_verdict
from app.research.records import score_records

TRACK_CACHE_SECONDS = 60
_track_cache: dict[str, tuple[float, str]] = {}


def track_kind(engine, settings: Settings) -> str:
    """"too_few", "ahead" or "no_edge": the Dashboard's message about the scores (the same function), cached for a minute."""
    key = str(engine.url)
    cached = _track_cache.get(key)
    if cached and time.monotonic() - cached[0] < TRACK_CACHE_SECONDS:
        return cached[1]
    series = {e.ticker: (e.sport, e.league) for e in settings.sports_series}
    score = score_records(engine, None, series, settings.min_supported_claims)
    kind = track_verdict(score["games"], score["same_records"]["ours"], score["same_records"]["market"])["kind"]
    _track_cache[key] = (time.monotonic(), kind)
    return kind


def verdict(flagged: int, stale: bool, unavailable: bool, measured: bool | None, track: str, age_hours: float | None = None) -> dict:
    """{kind: no_bet | look_caution | look, label, text, caution}. `track` is the result of track_kind."""
    if unavailable:
        return {"kind": "no_bet", "label": "NO BET", "text": "NO BET: there is no forecast, or no price to compare it with.", "caution": None}
    if stale:
        old = "" if age_hours is None else f" {age_hours:.0f} hours"
        return {"kind": "no_bet", "label": "NO BET", "caution": None,
                "text": f"NO BET: the forecast is{old} old and cannot be flagged. Research the game again if you are interested."}
    if flagged == 0:
        return {"kind": "no_bet", "label": "NO BET", "text": "NO BET: no market passed all the tests.", "caution": None}
    parts = []
    if track == "too_few":
        parts.append("too few games have finished to show that our forecasts beat the Kalshi price (see the Dashboard)")
    elif track != "ahead":
        parts.append("our forecasts have not beaten the Kalshi price on finished games (see the Dashboard)")
    if measured is False:
        parts.append("this sport has no scored results yet: the flag has not been tested here")
    if parts:
        caution = "NO BET is the default: " + "; ".join(parts) + "."
        return {"kind": "look_caution", "label": "Worth a look", "text": f"Worth a look. {caution}", "caution": caution}
    return {"kind": "look", "label": "Worth a look", "text": "Worth a look. This is not a recommendation.", "caution": None}
