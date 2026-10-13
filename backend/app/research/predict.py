"""Combines the forecasters' probabilities into one probability per outcome: the median, with the spread.

The median is used because one odd forecaster cannot pull it far. The spread (largest minus smallest
estimate) and every single estimate are kept, so a reader can see how much the forecasters agreed.
With fewer than two valid forecasts there is no prediction and the record says why."""

from statistics import median

from app.research.forecast import ForecastSet
from app.research.schemas import GameInfo


def build_prediction(game: GameInfo, forecast_set: ForecastSet, supported_claims: int) -> dict:
    adjustments = [{"forecaster": f.index + 1, "note": n} for f in forecast_set.forecasts for n in f.adjustments]
    base = {
        "markets_not_offered": game.group_notes,
        "adjustments": adjustments,  # small inconsistencies between related markets that were fixed
        "forecasters_valid": len(forecast_set.forecasts),
        "dropped": forecast_set.dropped,
        "evidence": forecast_set.evidence,
        "supported_claims": supported_claims,
    }
    if not forecast_set.ok:
        return {"unavailable": forecast_set.unavailable_reason} | base

    raw = {t: median(f.probabilities[t] for f in forecast_set.forecasts) for t in game.market_tickers}
    total = sum(raw[t] for t in game.outcome_tickers)  # only the winner outcomes add up to 100%
    outcomes = []
    for title, ticker in zip(game.market_labels, game.market_tickers):
        winner = ticker in game.outcome_tickers
        values = [f.probabilities[ticker] for f in forecast_set.forecasts]
        outcomes.append({
            "market_ticker": ticker,
            "kind": game.kind_of(ticker),
            "outcome": title,
            # Medians of separate vectors need not add up to exactly 100%; where exactly one outcome
            # happens they are scaled to do so. The unscaled median is kept.
            "probability": round(raw[ticker] / total if (game.sums_to_one and winner) else raw[ticker], 4),
            "median_raw": round(raw[ticker], 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "spread": round(max(values) - min(values), 4),
            "forecasts": [{"variant": f.variant, "probability": round(f.probabilities[ticker], 4)} for f in forecast_set.forecasts],
        })
    return {"outcomes": outcomes} | base
