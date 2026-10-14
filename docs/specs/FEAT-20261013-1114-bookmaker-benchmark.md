# Spec: bookmaker odds as a third benchmark (FEAT-20261013-1114)

Branch `feature/sports-games-list` (base `master`). For approval; nothing here is built yet.

## Why (the need behind the request)

The client's question is whether the system finds genuine opportunities. Kalshi's price is one benchmark, and so far it beats us (first scores, 15 games: ours 0.192, plain AI 0.222, Kalshi 0.154). Bookmakers are the other well-known benchmark: the consensus of many books, with the margin removed, is a standard "what the informed market thinks". Two uses: (1) if the bookmaker consensus differs from Kalshi, Kalshi may be mispriced, a different kind of opportunity than "our model disagrees"; (2) if we ever beat Kalshi but not the books, we have learned something about Kalshi, not about our forecasts. Scraping bookmaker pages failed (403 walls), so we need an odds feed.

## What I verified (2026-10-14, with the free key; nothing paid)

- The Odds API `GET /v4/sports` (free, 0 credits) lists sport keys and which are active. Active today: `soccer_epl`, `soccer_uefa_champs_league`, `soccer_usa_mls`, many other leagues, `baseball_mlb`, `baseball_npb`, `baseball_kbo`, `tennis_atp_shanghai_masters`, `tennis_wta_wuhan_open`, NBA, WNBA, EuroLeague, NBL. Tennis keys exist **per tournament** and only while it runs. **No Challenger keys**: most of our tennis games (Challengers) get no bookmaker price.
- One call `GET /v4/sports/soccer_uefa_champs_league/odds?regions=eu&markets=h2h` costs 1 credit and returned all 9 upcoming games, each with 45 to 46 bookmakers (including Pinnacle, Betfair exchange, DraftKings, FanDuel). With `regions=us,uk,eu` it costs 3. The free plan gives 500 credits a month and the API reports credits left in headers. Historical odds are paid only, so the benchmark must be **recorded at forecast time** (which is exactly how our records already work).
- Naive name matching of Kalshi game titles to the feed matched 7 of 9 Champions League games by team names plus start time within 3 hours; the 2 misses were `Bodoe/Glimt` vs `Bodø/Glimt` and `PSG` vs `Paris Saint-Germain`.
- In code: `OutcomeRecord` holds the frozen forecast and market at forecast time (`build_records` in `backend/app/research/records.py`); `score_records` compares ours, the plain AI and the Kalshi middle on "the records that have all three".

## Design

1. **Setting.** `ODDS_ENABLED` (default false) and `ODDS_API_KEY` (a secret, only in `.env`). With `ODDS_ENABLED=true` and the key missing, the app refuses to start and says so (as for Telegram). `ODDS_REGIONS` default `eu` (1 credit per sport per call; Pinnacle and the European books are in it).
2. **A small client** `app/odds.py` (plain `httpx`, already installed): list active sport keys, fetch the odds of one sport key. The key never appears in logs or errors (query parameter hidden, only the error kind is kept, like `telegram.py`). The credits left are read from the response headers and logged; when fewer than 50 remain it logs a warning and when 0 remain it stops calling and says why in plain words (explicit, named fallback).
3. **Which sport key.** From the game's league label (the series in `SPORTS_SERIES`): soccer and baseball leagues map to fixed keys (a small table in code: EPL, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, NPB, KBO); ATP and WTA map to whichever `tennis_atp_*` or `tennis_wta_*` key is active that day (from the free sports list); Challengers have none, so the record says "no bookmaker source for this league" and nothing is guessed.
4. **Matching a game.** Team names normalised (accents, case, club words like FC/AS) plus a small alias table (`Bodoe/Glimt`, `PSG`, ...), and the start time within 3 hours; exactly one feed game must match. No match or two matches: no bookmaker price, with the reason saved. Never a low-confidence guess. The match rate is printed by `score-records` so a poor matcher is visible.
5. **The price.** For each bookmaker's head-to-head prices, take the implied probabilities and remove the margin by scaling them to sum to 1 (the simplest standard method; its limits, favourite-longshot bias, are noted in the notes). Consensus = the median across bookmakers, excluding exchanges (their prices have no margin but a commission). Also save Pinnacle's own margin-free probability when present (the sharpest single book) and the number of bookmakers used. Only "winner" markets (head-to-head) in this first version; totals, spreads and both-teams-to-score need other markets (more credits) and are a later step.
6. **Where it is saved.** New nullable columns on `outcome_records`: `book_probability`, `book_pinnacle`, `book_count`, `book_at`, `book_note` (reason when absent). Filled when the record is made (same moment as the Kalshi price), by the existing record step, once per game; one odds call per sport key is cached for 10 minutes (`ODDS_CACHE_MINUTES`) so researching 10 games of one league costs 1 credit. A failure of the odds call never fails the run or the record: the forecast is saved without a bookmaker price and the reason (a named, logged fallback).
7. **Scoring.** `score_records` adds the bookmaker consensus to the comparison on the records that have it (so "all four" for winner markets that matched), prints the number of records and games it covers, and the Pinnacle score where available. The existing three-way numbers and the headline stay as they are.
8. **Cost.** Free plan: 500 credits a month. At one credit per sport key per 10 minutes with caching, 30 researched games a day in about 8 leagues costs about 10 to 30 credits a day: it can exceed 500 a month, and then the paid plan ($30 a month, 20,000 credits) fits easily. The credits left are shown by the command so nobody is surprised.

## Not changed or not done

- Alerts, flags and the Opportunities page do not use bookmaker prices in this step (a bookmaker-vs-Kalshi gap as a flag reason is a later decision, after we see the scores).
- Totals, spreads and both-teams-to-score from the feed; Challenger tennis (no source found); the paid historical odds.
- The research step's own "market odds" angle is unchanged.

## Terms and risks

The Odds API terms allow research and analysis use and storing data (read 2026-10-14, summary from the vendor's terms page; I did not see a country restriction, and the client's use is private research). Margin removal by scaling is a simplification. Name matching is the weakest part: it is measured, not trusted.

## Tests

Hand-worked margin removal and consensus (median, exchanges excluded, Pinnacle kept); name matching with accents, aliases, a no-match and a two-match case; the start-time window; a fake odds client for: key hidden from logs and errors, credits low warning, zero credits stop, caching (one call for several games), failure leaves the record without a bookmaker price and with the reason; startup refuses `ODDS_ENABLED=true` without a key; the record columns migrate and old records keep working; `score_records` with and without bookmaker data.

## Checks to state at close

Lateral spread: every place that creates or reads `outcome_records` (record step, resolve, score, the compact forecast and the alerts do not read it). Causal depth: the need is "is Kalshi or are we closer to the truth"; the bookmaker benchmark covers winner markets in leagues the feed lists; Challenger tennis and the other market kinds stay uncovered and the scores must say so.
