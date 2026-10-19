# Spec: the price test at other horizons (24 hours, 7 days, 14 days before the start)

Branch `feature/sports-games-list` (base `master`). Follow-up of the price test (`docs/discussion/PRICE-TEST-2026-10-19.md`, no pattern found one hour before the start) and of the signal research (`docs/discussion/SIGNAL-RESEARCH-2026-10-19.md`, idea 2): the studies say Kalshi's prices are least accurate far from the event, so the question is whether the price is biased or exploitable **further out**. Free, read-only, no model, nothing ordered.

## What is there now (read in `research/pricetest.py`)

The test takes the bid and ask in the last hourly candle at least one hour before the start. The sample (every k-th game, at most 400 per series), the start times and the market lists are in the on-disk cache, so the same games can be read again without downloading them. The market lists in the cache do not hold each market's opening time.

## Design

- **Horizons, fixed now:** 24 hours, 7 days (168 hours) and 14 days (336 hours) before the start, besides the one hour already done. `price-test --horizons 24,168,336`; the default stays one hour so the first test is unchanged.
- **Same games, same rule.** The same sampled games (so the numbers are comparable with the one-hour result); for each horizon the price is the last hourly candle ending at least that many hours before the start, with a bid and ask, a spread of at most 10 cents, in every winner market of the game. A game is dropped for a horizon if its markets did not exist yet then, or had no usable price; the report counts these per series and horizon (a market that opened after the horizon needs no request: the market lists now keep each market's opening time, so the first run of this test downloads those lists again and nothing else that is cached).
- **Measured at each horizon, as before:** calibration by 10-cent bucket, the Brier score of the middle price, and strategies F, L and N (the definitions are unchanged: one contract at the ask with the series fee).
- **One extra number per horizon: how much more accurate the price becomes as the game nears,** the Brier score of the price at that horizon against the one-hour price on the same games. It shows how much information arrives late and is descriptive only (nothing is tested on it).
- **Which results are tested (the rule):** only the pooled group and the four sectors (soccer, tennis, baseball, basketball), not each series: 5 groups, 3 strategies, 3 horizons = 45 comparisons. The first half of the games (by start date) is for looking, the second half confirms; a pattern is FOUND only if the second half's average after fees is above zero with the lower end of its **99 percent** interval above zero (resampling whole games, seed 20261017) and the first half is also above zero. The per-series rows are shown but are descriptive. No other strategy is tried after seeing the numbers.
- The report states the same limits as the first one and, for each horizon, the median spread and the number of games with a usable price, because far-out markets are thin and a price with a wide spread is not a price one can trade at.

## Not done

No bookmaker data (paid), no strategy beyond F, L and N, no horizon beyond 14 days, no markets other than the winner markets, no change to the app.

## Tests

Backend, mocked Kalshi (no network): the price is chosen at the requested lead (a candle too close to the start is skipped at each horizon); the candle window and the cache key depend on the lead (a second horizon does not reuse the one-hour candles by mistake); a market that opened after the horizon is dropped without a request and counted; the horizons option is parsed and the default is one hour; the report has one section per horizon with the accuracy gain against the one-hour price; the rule's `FOUND` and `not confirmed` cases at a horizon; the sector groups only are tested.
The real run is a separate step after the tests; its report is committed whatever it says.

## Checks to state at close

Lateral spread: the price-choosing and fee code is shared with the first test, so the one-hour result must come out the same as before on the cached games (compared). Causal depth: the question is whether the price is exploitable further out; the horizons, the strict interval for 45 comparisons, the selection of which games have a price at each horizon, and the descriptive information-arrival number are each reported.
