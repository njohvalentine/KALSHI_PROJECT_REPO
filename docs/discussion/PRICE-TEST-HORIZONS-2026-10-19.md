# Kalshi price test at other horizons, reading of the result (2026-10-19)

The raw tables are in `docs/discussion/PRICE-TEST-HORIZONS-RAW-2026-10-19.md`. The test and its rule were written before the run: `docs/specs/FEAT-20261019-0956-price-test-horizons.md` (follow-up of `docs/discussion/PRICE-TEST-2026-10-19.md`, which found no pattern one hour before the start). Free, read-only: no model call, nothing ordered.

## The result in one paragraph

**At 24 hours, 7 days and 14 days before the start, on the same sampled games, no pattern was found.** Of the 45 pre-registered comparisons (the pooled group and four sectors, three strategies, three horizons), none passed the rule (second half above zero with the lower end of its 99 percent interval above zero, and a positive first half). Several looked fine in one half and not in the other, which the rule counts as "not confirmed". The price a week or two before a game is **almost as accurate as the price an hour before**, so the idea that far-out sports prices are noticeably off does not show up here.

## Which games had a price at each horizon

A single game's markets do not exist long before the game. This limits what can be said:

| Horizon | Games with a usable price | Of which soccer | Median spread |
|---|---|---|---|
| 1 hour (first test) | 4,709 | 2,524 | not recorded in that report |
| 24 hours | 3,306 | 2,467 | 1.0 cent |
| 7 days | 1,431 | 1,426 | 3.0 cents |
| 14 days | 170 | 170 | 3.0 cents |

At 7 and 14 days only soccer has enough games (most tennis, baseball and basketball markets opened only a day or two before the game: 2,695 games had a market that was "not open 7 days before the start", 4,308 at 14 days). So the 7-day result is a soccer result, and the 14-day result is 170 soccer games, too few to see anything but a large effect.

## Accuracy: the price barely improves as the game nears

On the games that have a price at both times (Brier score of the middle price, lower is better):

| Horizon | Games | Price at the horizon | Price one hour before |
|---|---|---|---|
| 24 hours | 3,297 | 0.1963 | 0.1960 |
| 7 days | 1,430 | 0.1942 | 0.1933 |
| 14 days | 170 | 0.1883 | 0.1894 |

The differences are under 0.001, smaller than any noise in this sample. Whatever the studies say about prices more than a month before an event, for the horizons a single game allows (up to about two weeks) the price is as good as the closing price.

## Calibration

At 24 hours the price is well calibrated: the largest gap in any bucket is under 3 points for the busy buckets (the 90–100¢ bucket has 35 outcomes and a 4-point gap, too few to read). At 7 days two buckets differ by about 5 points (50–60¢ happened 0.496 of the time against a 0.546 price on 365 outcomes; 60–70¢ happened 0.688 against 0.643), in opposite directions, which looks like noise rather than a bias. At 14 days the buckets hold too few outcomes (3 to 57 each, apart from 20–30¢) to say anything.

## The strategies

Pooled, second half, after fees (each 99 percent interval includes zero):

| Horizon | Favourites (F) | Buy longshots (L) | Buy "no" on longshots (N) |
|---|---|---|---|
| 24 hours | -2.0¢ | -1.5¢ | -1.5¢ |
| 7 days | -3.5¢ | -3.4¢ | -3.1¢ |
| 14 days | -7.8¢ | -7.3¢ | -1.1¢ |

All are negative. The cost grows with the horizon because the spread widens (1 cent at 24 hours, 3 cents at 7 and 14 days), and the fee is the same. The 14-day figures rest on 170 games and wide intervals.

## What this means

1. The price test is closed for single games: **no bias to exploit in Kalshi's single-game sports prices, from an hour to two weeks before the start, on thousands of games.** This covers the idea "a pattern in the price".
2. The literature's far-out inaccuracy (prices pulled toward 50/50, strongest beyond a month) concerns events that are open for weeks or months, such as season and futures markets. Those are a different product from "research a game" and are not tested here.
3. What is left, from the signal research, is timing (reacting to news) and how orders are placed. Neither can be tested with this data.

## Limits (to state whenever this is quoted)

- The prices are hourly bid and ask closes, not executable fills; the contracts offered are unknown for the past.
- Only games settled before Kalshi's history cutoff of 2026-08-18.
- The same selection note as the first test: games with no single winner (472 across series, mostly tennis retirements) were left out.
- At 7 and 14 days the result is soccer only; 14 days is 170 games.
- The rule looks only for patterns that make money.

## Decision

Nothing in the app changes. The horizon extension is closed as "no pattern found". Option A (30 dollars of bookmaker history) is not recommended on the strength of this result: the bookmakers match Kalshi within fees in our own check, and the history would test the same kind of price pattern with an extra cost.
