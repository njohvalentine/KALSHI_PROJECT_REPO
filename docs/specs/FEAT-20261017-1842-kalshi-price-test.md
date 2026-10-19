# Spec: a free price-only test on Kalshi's own history (option B)

Branch `feature/sports-games-list` (base `master`). Option B of `docs/discussion/HISTORICAL-DATA-2026-10-17.md`, chosen by the user on 2026-10-17. It answers one question that does not depend on our AI: **is Kalshi's price an hour before a game biased in a way that could be exploited after fees?** It cannot say anything about our forecasts (they are tested live).

## Design

**A read-only command** `price-test` (in `app/cli.py`, code in `app/research/pricetest.py`), like the replay tool: it reads Kalshi's public history, writes a report, and writes nothing to the database. No new dependency, no model call, no OpenAI credit, no order of any kind (the existing test that forbids outgoing POSTs covers the new code). Three read-only methods are added to `KalshiClient` (list historical markets, historical candlesticks, normal candlesticks for recent markets if needed), all GET.

**Collection** (cached on disk in a git-ignored folder so a re-run downloads nothing again):
1. For each series in the list below, page `GET /historical/markets?series_ticker=...` (settled markets older than 2026-08-18, from the cutoff endpoint) and keep, per game (event), the winner markets with their result (yes or no).
2. Keep a fixed sample per series: **every k-th game in order of settlement, to at most 400 games** (k chosen so the sample is spread over the whole period; no random choice). 14 series give at most about 5,600 games and about 17,000 requests (a few hundred per minute at most, with a pause between them to be polite; the documentation states no rate limit).
3. For each sampled game, the start time comes from `GET /milestones?related_event_ticker=...` (checked on four games: it holds the real start for old games too; a market's own time is the settlement time and is not used). For each of its winner markets, the hourly candles from 3 hours before to 1 hour before the start (`GET /historical/markets/{ticker}/candlesticks`, period 60).

**The series** (all winner series that the app handles): Premier League, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, NBA, ATP, WTA, ATP Challenger, WTA Challenger.

**The price used.** The last candle that ends at least one hour before the start and has a bid and an ask. A game is kept only if every winner market has a price with `0 < bid <= ask < 1` and a spread of at most 10 cents, and a result. The counts of games dropped, with the reason, are in the report (no start time, no price, a wide spread, no result, a voided market).

**What is measured** (per series, per sector and pooled):
1. *Calibration:* markets in price buckets of 10 cents (by the middle of bid and ask): how many, the mean price, how often the outcome happened.
2. *Accuracy:* the Brier score of the middle price.
3. *Three simulated strategies, one contract each, bought at the ask, with Kalshi's fee for the series* (0.07 times the series multiplier times price times one minus price, as in the app): **F** buy "yes" on the favourite of each game (the outcome with the highest middle price); **L** buy "yes" on every outcome with a middle price of 20 cents or less (longshots); **N** buy "no" on every outcome with a middle price of 20 cents or less (the other side of the same longshots).
4. For each strategy: bets, wins, the average result per contract after fees, and a 95 percent and a 99 percent interval of that average by resampling **whole games** (2,000 resamples, seed 20261017), because the outcomes of one game are not independent.

## The rule (written before the run)

- The sample of each series is split by start date: the **first half is only for looking, the second half confirms**.
- A pattern **counts as found only if, in the second half, the average result after fees is above zero and the lower end of the 99 percent interval is also above zero, and the first half has the same sign.** 99 percent, because 3 strategies in 19 groups (14 series, 4 sectors and all games pooled) are 57 comparisons and at 95 percent about three would pass by chance. (The first version of this spec said 45; it forgot the four sector groups. The rule is unchanged.)
- Anything else is reported as "no pattern found" or, for a result that looks good in the first half only, as "not confirmed". No other strategy is tried after seeing the numbers (an added strategy would be a new item with its own rule).
- The report states, whatever the result: the number of games, the period, and that the prices are hourly bid and ask closes of the markets, not executable fills (the contracts offered at the ask are not known for the past), so a pattern that passes is a reason for a live check and not proof of profit.

## Not done

No bookmaker data (option A, which costs money); no test of the AI research; no use of the result to change the app's rules (a confirmed pattern would be a new item); only games settled before the history cutoff of 2026-08-18 (newer ones are on other endpoints and can be added later); no totals, spreads or both-teams-to-score markets.

## Tests

Backend, with the Kalshi calls mocked (no network): the sample is every k-th game and never more than 400; the start time comes from the milestone; the last usable candle at least an hour before the start is chosen, and a game with a wide spread, no price or a voided market is dropped with its reason; calibration buckets; the fee per series; strategies F, L and N on a small set of games with known results; the interval is by whole games (a duplicated game does not tighten it) and reproducible with the seed; the rule: confirmed, not confirmed and no pattern cases; the cache means a second run makes no requests; the command writes no database row and no request other than GET (the test that forbids POSTs). The real run is a separate step, with the report committed afterwards, whatever it says.

## Checks to state at close

Lateral spread: the new Kalshi methods are GET only and go through the same retry code; the cache folder is git-ignored. Causal depth: the question is "is Kalshi's price exploitable", so the test has a rule fixed in advance, a confirming half, a strict interval for the number of comparisons, and the statement of what the data cannot show.
