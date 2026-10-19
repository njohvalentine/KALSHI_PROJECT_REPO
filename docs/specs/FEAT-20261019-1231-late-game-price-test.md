# Spec: a free test of the last minutes of a market ("buy NO on 10 to 40 cent contracts near the close")

Branch `feature/sports-games-list` (base `master`). Follow-up of the signal research (`docs/discussion/SIGNAL-RESEARCH-2026-10-19.md`) and of a second analysis session's lead. Free, read-only, no model, nothing ordered. Same style as the price test: the rule is written here **before** any run.

## Where the idea comes from, and what the paper really says

The paper is "Prices, Probabilities, and Parlays" (Moshrefi, arXiv 2607.14430, 15 July 2026). I read the full text, not only the summary the other session sent. What it says, and what it does not:

- **Late game (the lead).** Data: 23 million moneyline trades, NBA, MLB and NHL only, early March to mid May 2026 (7 to 11 weeks per league). Prices in the middle of a contract's life are well calibrated, which agrees with our price test. In the **last 10 minutes before the market close** the calibration curve becomes step-like. The sentence behind the lead is about the **NHL** chart: "contracts trading at 10 to 40 cents in the final ten minutes resolve favorably almost never". For the NBA the distortion is much milder (Platt slope 1.62 against 4.56 for the NHL).
- **What the paper does not do.** It uses executed trade prices and says plainly that prices **exclude fees**. It does not test a strategy, and it says other causes (informed traders leaving, late uninformed traders) cannot be ruled out with its data.
- **The big catch (look-ahead).** "Time to expiry" is measured to the market's **close time**, which the paper says "coincides with the end of the game". That time is only known afterwards. A trader in the game cannot know that this is the last 10 minutes. So the paper's result can be true and still not tradable. In our own cached history the gap between the start and the close varies a lot for NBA (148 to 178 minutes), MLB (149 to 260) and tennis (80 to 172), so the close time there is the real end. For soccer it is a fixed 120 minutes after the start, so it is not the real end. A short probe I made (6 markets) also showed that, in the last half hour before the close, many quotes are already 0.00/0.01 or 0.99/1.00: the result was known and the market was still open.
- **Combos (not part of this item).** The paper's own table: the median overpricing is 0.991, 0.995 and 0.999 for 2, 3 and 4 legs (fair), 1.005 for 5 legs, 1.07 for 8, 1.22 for 10. The "about 3% per leg" is a straight-line fit over 2 to 11 legs, not a flat markup per leg. Their sample was legs 30 to 240 minutes before the close, cross-game only. So "the client's 17-leg tickets are the worst case" is a fair reading of the direction, but "3% per leg" is not what the data shows. This goes into the client wording later, not into this test.

## What is there now (read in `research/pricetest.py` and `kalshi.py`)

- The on-disk price-test cache holds the market lists (with each market's close time and result), the start times and the sampled games (4,709 games, 14 series: 8 soccer leagues, MLB, NBA, 4 tennis tours). There is no NHL series in it.
- `KalshiClient.get_historical_candlesticks(ticker, start_ts, end_ts, period_interval=1)` exists. I probed it on three series: it returns 1-minute candles with bid and ask for the last half hour before the close (28 to 30 of 30 candles with both), with traded volume per candle. Depth (how many contracts can be bought at the ask) is **not** available in history.
- `bootstrap`, `verdict`, `Cache`, `patient`, `_num`, the fee code and the sample are reusable as they are.

## Design

**Two stages, and the second one only if the first passes.**

*Stage 1 (this spec): the paper's question, in hindsight, after costs.* Does buying NO on a 10 to 40 cent contract in the last minutes before the close make money at the price you would really pay, with fees? It uses the real close time, so it is **not tradable** and is not presented as such. If it fails here it fails everywhere, and we stop and say so. If it passes, that earns a second spec (stage 2) for a tradable trigger.

The rule, fixed now:

- **Games:** the same cached sample of games (so comparable with the earlier tests), every winner market in them. A game is kept only if its close time is a real end: the series where the cached close minus start is **not** nearly constant (a median absolute deviation below 5 minutes) are excluded and the report names them (expected: the soccer leagues). Reason: for those the "last 10 minutes" would be a fixed clock time and not the end of the game.
- **Entry price:** the last 1-minute candle ending at least **5 minutes** before the close that has a bid and an ask. 5 minutes is the middle of the paper's 10-minute window and is fixed before looking. The report also shows 10 minutes and 2 minutes before the close as descriptive rows; they are **not** tested.
- **Bet:** one contract of NO on every outcome whose YES middle price is from 10 to 40 cents inclusive at that candle, bought at the NO ask (1 minus the YES bid) plus the series' taker fee, held to the result.
- **Kept only if:** the YES spread is at most 10 cents, and at least **10 contracts traded in the 5 minutes before** that candle (a stand-in for "someone is really trading", because depth is not in the history). Dropped bets are counted by reason. The volume filter is part of the rule from the start, not added after seeing the numbers.
- **Groups tested:** pooled, and the sectors that remain after the exclusion above. That is at most 5 comparisons.
- **Halves and verdict, as in the price test:** first half of the games by start date for looking, second half for confirming; resampling whole games, seed 20261017. FOUND only if the second half's average after costs is above zero with the lower end of its **99 percent** interval above zero **and** the first half is above zero, **and** each half has at least 100 bets (otherwise "too few bets"). No other price band, minute or strategy is tried after seeing the numbers. If a different version looks interesting, it needs its own spec and fresh data.
- **Honest limits stated in the report:** hindsight close time; no depth; minute candle bid and ask closes are not fills; a quote left standing after the result is known (the 0.00/0.01 case) cannot be bought, so the report counts bets whose quote did not change in the five minutes before the entry; fees as the series says (the soccer and tennis fee types differ).

*Stage 2 (not in this spec):* a tradable version. It needs a live trigger that does not use the close time (for example the clock since the start plus a score feed), and it needs data that was not used to choose the rule: forward minute prices collected from now on. Without a live score source it cannot be built, and that would be said at that point.

## Implementation

- New module `app/research/latetest.py` (reusing the pricetest pieces) and CLI command `late-test` (options: `--cache-dir`, `--out`, `--workers`). Minute candles of the last 30 minutes before the close per market are cached on disk under their own key (`late-candles-{ticker}`), so a second run downloads nothing. One request per market with a pause and the same patient retries; about 9,000 requests, run in the background. Writes a report to `docs/discussion/LATE-TEST-<date>.md` (and the raw output beside it), committed whatever it says. Writes no database row and places nothing.
- No new setting, no new dependency, no migration, no change to the app.

## Not done

No NHL (not in the cache; adding it is a separate decision), no combos, no live trigger, no other strategies, no depth data, no change to the app or the client's screens.

## Tests

Backend, mocked Kalshi, no network: the entry candle is the last one ending at least 5 minutes before the close with both sides; the bet is NO at 1 minus the YES bid plus the fee, with the right result on a win and a loss; the 10 to 40 cent band edges; the spread and volume filters and their dropped counts; the near-constant close series are excluded and named; the minute-candle cache key; the `FOUND`, `not confirmed`, `no pattern` and `too few bets` verdicts; the CLI option parsing.
The real run is a separate step after the tests.

## Checks to state at close

Lateral spread: the same look-ahead question applies to any other idea that uses the close time (it is stated in the report; the earlier price tests used the start time, so they are unaffected). Causal depth: a pass could come from stale quotes, from thin books, from the NHL-like cases being absent from our data, or from chance in 5 comparisons; each is either counted in the report or covered by the 99 percent interval, and none is claimed away.
