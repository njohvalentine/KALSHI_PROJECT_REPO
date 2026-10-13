"""Combines the forecasters' probabilities into one probability per outcome: the median, with the spread.

The median is used because one odd forecaster cannot pull it far. The spread (largest minus smallest
estimate) and every single estimate are kept, so a reader can see how much the forecasters agreed.
With fewer than two valid forecasts there is no prediction and the record says why."""

from statistics import median

from app.research.forecast import ForecastSet
from app.research.schemas import GameInfo


def build_prediction(game: GameInfo, forecast_set: ForecastSet, supported_claims: int) -> dict:
    base = {
        "forecasters_valid": len(forecast_set.forecasts),
        "dropped": forecast_set.dropped,
        "evidence": forecast_set.evidence,
        "supported_claims": supported_claims,
    }
    if not forecast_set.ok:
        return {"unavailable": forecast_set.unavailable_reason} | base

    raw = {t: median(f.probabilities[t] for f in forecast_set.forecasts) for t in game.outcome_tickers}
    total = sum(raw.values())
    outcomes = []
    for title, ticker in zip(game.outcomes, game.outcome_tickers):
        values = [f.probabilities[ticker] for f in forecast_set.forecasts]
        outcomes.append({
            "market_ticker": ticker,
            "outcome": title,
            # Medians of separate vectors need not add up to exactly 100%; where exactly one outcome
            # happens they are scaled to do so. The unscaled median is kept.
            "probability": round(raw[ticker] / total if game.sums_to_one else raw[ticker], 4),
            "median_raw": round(raw[ticker], 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "spread": round(max(values) - min(values), 4),
            "forecasts": [{"variant": f.variant, "probability": round(f.probabilities[ticker], 4)} for f in forecast_set.forecasts],
        })
    return {"outcomes": outcomes} | base
