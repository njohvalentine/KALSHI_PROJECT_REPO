# Kalshi price test, reading of the result (2026-10-19)

The raw tables are in `docs/discussion/PRICE-TEST-RAW-2026-10-19.md`. The test and its rule were written before the run: `docs/specs/FEAT-20261017-1842-kalshi-price-test.md`. Nothing was paid, nothing was ordered, and no model was called.

## The result in one paragraph

**On 4,709 finished games in 14 series (April 2025 to August 2026), Kalshi's price an hour before the start was well calibrated, and none of the three simple strategies made money after fees, in any series, any sport, or overall. No pattern was found.** The pre-registered rule asked for a positive average in the second half of the games, with the lower end of the 99 percent interval also above zero, and a positive first half. No group of 19 and no strategy of 3 passed (57 comparisons). That is what the studies of Kalshi near the event predict, and what our bookmaker check and our own 62 games already suggested.

## What was measured

- **Games:** 4,709 kept out of a fixed sample of every k-th game per series (at most 400 each): 2,524 soccer games (eight leagues), 1,452 tennis matches (ATP, WTA and both Challenger tours), 372 MLB games, 361 NBA games.
- **Price:** the bid and ask in the last hourly candle ending at least an hour before the start. A game was kept only if every winner market had a bid and ask, a spread of 10 cents or less, and a clear winner.
- **Strategies (one contract at the ask, with Kalshi's fee):** F buy "yes" on the favourite; L buy "yes" on every outcome priced at 20 cents or less; N buy "no" on those same outcomes.

## Calibration: the price says what happens

All 4,709 games pooled, by the price bucket:

| Price | Outcomes | Mean price | How often it happened |
|---|---|---|---|
| 0–10¢ | 355 | 0.070 | 0.056 |
| 10–20¢ | 1,406 | 0.157 | 0.151 |
| 20–30¢ | 3,104 | 0.252 | 0.253 |
| 30–40¢ | 1,929 | 0.343 | 0.328 |
| 40–50¢ | 1,621 | 0.446 | 0.471 |
| 50–60¢ | 1,399 | 0.549 | 0.543 |
| 60–70¢ | 1,042 | 0.647 | 0.636 |
| 70–80¢ | 615 | 0.745 | 0.741 |
| 80–90¢ | 358 | 0.841 | 0.866 |
| 90–100¢ | 113 | 0.933 | 0.947 |

The largest gap in any bucket is under 3 points. The cheapest prices (under 10 cents) happen slightly less often than priced, the direction the Kalshi studies report (a small longshot bias), but the gap (1.4 points) is smaller than the fee and the spread.

## The strategies

| Strategy | Games | Second-half average after fees | 99% interval |
|---|---|---|---|
| F, favourites | 4,709 | -1.8¢ | -4.3¢ to +0.7¢ |
| L, buy longshots | 4,709 | -1.6¢ | -4.5¢ to +1.5¢ |
| N, buy "no" on longshots | 4,709 | -1.3¢ | -4.5¢ to +1.5¢ |

(Pooled over all games; the per-series and per-sport rows are in the raw file.) Every pooled average is negative and every interval includes zero. In none of the 57 comparisons did the second half confirm a positive result. Several groups looked positive in one half and not in the other, which is what chance looks like, and the rule counted them "not confirmed".

**One negative worth stating:** buying Premier League favourites lost 10.7 cents per contract in the second half (99% interval -19.7 to -1.2 cents). It is one of 57 comparisons, the rule looks only for positive patterns, and the other soccer rows do not show it, so it is not a pattern we can use. If anyone wants to test "sell favourites in the Premier League", it needs its own rule written first and new data (the next seasons).

## What this means

1. **No structural bias to exploit in Kalshi's pre-game sports prices an hour before the start, on thousands of games.** This closes the idea of "a pattern in the price" for this horizon and these simple strategies. It does not say that no pattern exists at other times or in other markets.
2. **It agrees with the rest of the evidence:** the bookmakers match Kalshi within fees, our forecasts add nothing to the price, and published studies of Kalshi find prices well calibrated near the event.
3. **Where the study says prices are less accurate is further from the event:** the next test, already logged, looks at 7 and 14 days before the start.

## Limits (to state whenever this is quoted)

- The prices are hourly bid and ask closes, not executable fills; the contracts offered are unknown for the past.
- Only games settled before Kalshi's history cutoff of 2026-08-18 were read.
- **Games with no single winner were left out:** 138 ATP and 122 WTA matches (retirements and walkovers that settled without a winner, most of them), 159 ATP Challenger and 25 WTA Challenger. If such markets refund, they cost nothing; if they are settled differently, the strategies would see a different result. This is a selection the test cannot rule out.
- MLB had no outcome priced at 20 cents or less, so strategies L and N have no bets there.
- The rule looks only for patterns that make money. A pattern that loses (like the Premier League favourites above) is reported but not tested further.

## Decision

Nothing in the app changes. The price test is closed as "no pattern found". The extension to 7 and 14 days before the start stays a logged item, to be done next.
