# What historical data exists, what it costs, and what it can and cannot show

Checked on 2026-10-17. Everything below was tested directly (read-only) unless it says otherwise. Nothing was bought. This answers the client's first priority of 2026-10-16: "Expand historical testing and demonstrate whether our forecasts can outperform Kalshi and bookmaker probabilities."

## The short answer

- **Kalshi's old prices are free and complete enough to use.** About 14 months of finished sports markets are available with hourly bid and ask prices, without any login.
- **Bookmaker history costs money.** The Odds API refuses our free key (checked: error `HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN`, at no credit cost). The cheapest paid plan is 30 US dollars a month. One month would be enough.
- **A test of the AI research on past games cannot be made fairly,** whatever the data costs. The reason is in section 4.
- **What can be tested on the past is prices only:** is Kalshi's pre-game price biased in some way, do the bookmakers beat Kalshi, and does buying where they disagree (the rule of the free check) make money after fees. That says nothing about our forecasts; our forecasts can only be tested live, as now.

## 1. Kalshi (free, no login)

- **Two tiers.** Recent markets are on the normal endpoints; older ones moved to history endpoints. `GET /historical/cutoff` gives the boundary: markets settled before **2026-08-18** are in the history tier (trades before the same date; orders before 2026-10-03). The history tier has the same pagination as the normal one.
- **What is there:** `GET /historical/markets` (one record per settled market), `GET /historical/markets/{ticker}/candlesticks`, `GET /historical/trades`. For recent markets the same candlesticks are on `GET /series/{series}/markets/{ticker}/candlesticks`.
- **Checked on real markets.** A recent finished WTA match (settled 2026-10-13) returned 24 hourly candles with bid, ask and traded price for the day before the game. An old Premier League market (2026-05-24) returned 29 hourly candles, all with a bid and an ask (for example 0.22 / 0.23 about a day before, 0.28 / 0.29 at the end). The two tiers name the fields differently (`close_dollars` and `close`); that is a detail for the code.
- **How far back and how many (counted in the history tier only, from the market lists):**

| Series | Markets in the history tier | Closed from | to |
|---|---|---|---|
| Premier League games | 1,161 (about 390 games, three markets each) | 2025-05-11 | 2026-05-24 |
| ATP matches | 8,580 (about 4,300 matches, two markets each) | 2025-06-18 | 2026-08-17 |
| MLB games | 8,190 (about 4,100 games) | 2025-04-16 | 2026-08-17 |
| NBA games | 2,898 (about 1,450 games) | 2025-04-16 | 2026-06-14 |

  Games after 2026-08-18 are on the normal endpoints, so the total is larger. These are counts of markets, not yet cleaned for games that were never played or have no usable price.
- **Limits of this data:** candles are hourly closes of the bid and ask, not an order book, so the contracts offered at the ask are not known for the past (the "at least 10 contracts" test of our rules cannot be applied to history). The rate limits for these endpoints were not stated in the documentation; the checks above made a few hundred requests without trouble.

## 2. The Odds API (bookmaker prices)

- **History exists from 2020** for the featured markets (head-to-head, totals, spreads), in 10-minute snapshots, and 5-minute snapshots from September 2022; ATP and WTA tournaments are included, **Challenger events are not mentioned**. (From the provider's documentation page.)
- **Our free key cannot read it.** A real call returned HTTP 401 `HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN` and cost nothing. One web page summary I read first claimed the free plan has history; it was wrong, the real call is the proof.
- **Price:** plans are Free (500 credits a month), **20K at 30 dollars a month (20,000 credits)**, 100K at 59 dollars (100,000 credits), and larger ones (from the provider's price list; check it again before paying).
- **Cost of history:** 10 credits for each region and each market per request, and one request returns all games of one sport at one moment. With one region (eu) and head-to-head only, one request is 10 credits. Games that start at the same time share a request. A rough estimate, not measured: 300 games would need at most about 300 requests, 3,000 credits, well inside one month of the 20K plan.
- **Matching games** between Kalshi and the feed was weak in today's live check: 32 of the 85 games that were not Challenger tennis found no match by team names and start time. This would have to be improved first, or the test would silently drop a third of the games and could be biased by which ones match.

## 3. What a price-only historical test could show

Pre-registered, so it cannot be adjusted after seeing the numbers.

**Test B (free, Kalshi only).** For every finished game of the series above, take the bid and ask one hour before the start and the result. Report, by sport and by price bucket: how often the outcome happened against the price (calibration), the Brier score of Kalshi's price, and the simulated result of buying the favourite and of buying the outsider at the ask after fees. A pattern counts only if it holds on a held-back half: the first half of the games (by date) is used to look, the second half to confirm, and the confirmed average result must be above zero with its 95 percent interval (resampling by game) also above zero.

**Test A (needs the 30-dollar month).** The same games, with the bookmakers' consensus an hour before the start (margin removed, as in the app). Report the Brier score of Kalshi against the bookmakers, and the simulated result of the rule of the free check (buy the side the bookmakers favour, at the Kalshi ask, when the gap after fees is at least 5 cents), with the same held-back rule.

**What neither test can show:** whether our AI forecasts are better than Kalshi or the bookmakers. They show whether *Kalshi's price* is exploitable, with or without the bookmakers, using thousands of games instead of the 62 we have.

## 4. Why the AI research cannot be tested on past games

The research step asks a model to search the web and then forecast. For a game that has been played:
- the model may remember how the game ended, and
- the web pages it finds often report the result, even when told to look for earlier information.

Either makes the forecast look better than it would have been before the game. We cannot prove the leak is absent, so a good result would not be believable and a bad one would be unfair. The live paper test (every forecast saved before the game starts) is the clean way, and it is running.

## 5. Options and costs

| Option | What it gives | Cost | Time |
|---|---|---|---|
| **B. Kalshi-only price test** | Is Kalshi's price biased or exploitable, by sport, on thousands of games | 0 | about 1 to 2 days of work |
| **A. B plus one month of the 20K plan** | The bookmakers against Kalshi, and the free check's rule tested on history | 30 dollars once (cancel after a month), plus the work of B and of better name matching | about 2 to 4 days |
| **C. Do nothing now** | Wait for the live paper test and the screenings to finish games | 0 | weeks |
| Test of the AI research on the past | Not possible fairly | not offered | — |

**Recommendation:** do B now; it is free, has the largest sample, and tests the one idea that does not depend on our AI (a structural pattern in Kalshi prices). Decide on A after B, and after the matching of games is improved, because A is the test of the client's question about the bookmakers and costs real money. Whatever is done, the answer to "do our forecasts beat Kalshi" stays with the live test.

## 6. Decisions needed

1. Does the operator want test B built (free)?
2. Does the client want to pay 30 dollars for one month of bookmaker history for test A, after B?
3. Is the pre-registered rule in section 3 acceptable to the client, or does he want different thresholds?
