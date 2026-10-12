# Spec: sports games list and research per game (FEAT-20261012-1426 and the four tasks after it)

Branch: `feature/sports-games-list` (base: `master`). The user asked for this work on a separate branch; merging is the user's decision.
Approved by the user on 2026-10-12: a configured league list, one row per game, buy and sell prices, game start time, a longer connect timeout, and one research run per game. Background and measurements: `docs/discussion/NOTEPAD.md`, D25.

## 1. Why

Kalshi offers no one-call "soccer, baseball and tennis games" filter. Measured on the user's VPN (D25): fetching every sports series is thousands of calls; paging all open events is 2 to 5 MB per page and slow; but single-match series follow a naming pattern (`...GAME`, `...MATCH`) and a list of about a dozen of them returned 620 open markets. On the live page a soccer game showed up as three loose outcome rows ("Newcastle wins", "Tie is the result", ...), with the last-trade price 0% where bids and asks exist, and Kalshi's `close_time` is days after kickoff.

## 2. Verified facts this spec relies on (live calls, public endpoints, 2026-10-12)

- `GET /events?series_ticker=S&status=open&with_nested_markets=true&limit=200`: one series returned its events in one page (EPL: 21 events, 150 KB, 5 s on the VPN). Event fields: `event_ticker`, `series_ticker`, `title` ("Coventry vs Newcastle"), `sub_title` ("COV vs NEW (Oct 12)"), `category`, `mutually_exclusive`, `markets`.
- Nested market fields used: `ticker`, `title` ("Newcastle wins"), `yes_sub_title` ("Newcastle"), `yes_bid_dollars`, `yes_ask_dollars`, `last_price_dollars`, `volume_fp`, `status` ("active"), `occurrence_datetime` (game time), `close_time` (trading closes, later than the game), `rules_primary` (full resolution text).
- `GET /events/{event_ticker}` returns `{event, markets}` with the markets at the **top level** when called without `with_nested_markets` (and inside the event with it).
- A soccer game has three markets (home, "Tie", away); tennis and baseball games have two.
- Prices are strings in dollars ("0.4300"); a zero last price with a real bid and ask is normal.
- A connection took 1.6 s and a small call 3.2 s on the VPN. The client's own network is likely faster (unmeasured).

Not verified: the exact list of series that exist for every league the client wants (the default list below was checked series by series in task 2); behavior when a game has started (open games already past their start time are shown and marked "Started").

## 3. Module 6 checks

- Lateral spread: every place that reads a run's `market_ticker`, `market_title` or a market-level `MarketInfo` is changed (run model and migration, runner, endpoints, prompts, researcher input, web app types and pages, tests). The `forecasts` table keeps `market_ticker` on purpose: forecasts will be per outcome market (Milestone 3).
- Causal depth: the user's slow-looking list had several causes, not one: combination markets (fixed earlier), a misleading price field, a misleading time field, markets shown as loose outcomes, no sport filter, and a connect limit too tight for slow networks. Each is covered by a task below.

## 4. Tasks

### Task 1 (FEAT-20261012-1426): Kalshi client
- `list_events(series_ticker, status, limit, cursor, with_nested_markets)` and `get_event(event_ticker)`; same retry and logging rules as the other calls.
- Timeouts: connect 6 s (was 3 s; too tight on a VPN), read 20 s (an events page took 5 s on the VPN), still 3 tries. Worst case for an unreachable host is about 20 s, shown by the loading state (it was 63 s before the earlier fix and 10 s after it; this trades some of that back for slow networks, and is noted here on purpose).
- Done when: path, parameter and response pass-through tests; a test of the new timeouts.

### Task 2 (FEAT-...): Games list service
- Setting `SPORTS_SERIES`: comma-separated entries `Sport:SERIES_TICKER:League label` (label optional). The default list is the verified series: soccer (EPL, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1 where it exists), baseball (MLB, NPB, KBO), tennis (ATP and WTA tour matches, ATP and WTA challenger). Malformed entries stop startup with a message (Module 4); the default is logged at startup. Also `GAMES_CACHE_SECONDS` (default 60) and `SPORTS_FETCH_CONCURRENCY` (default 6).
- The service fetches the open events of every configured series in parallel (at most `SPORTS_FETCH_CONCURRENCY` at a time; a shared thread pool and a lock so simultaneous page loads share one fetch), builds **one entry per game**, and keeps the result in memory for `GAMES_CACHE_SECONDS`.
- A game: `event_ticker`, `title`, `sub_title`, `sport`, `league`, `starts_at` (earliest `occurrence_datetime`), `closes_at` (earliest `close_time`), `started` (computed when served), and `outcomes`: `market_ticker`, `label` (`yes_sub_title`), `bid`, `ask`, `last`, `volume`.
- If a series call fails, the others still show and the response lists `errors` per series (visible on the page); a result with errors is cached for 10 s so a retry happens soon. No silent fallback to old data.
- **Games that already started are hidden by default** (a first live call showed games started 30+ hours earlier, still open on Kalshi until they settle, sorting above the upcoming ones); the response counts them (`hidden_started`) and `include_started=true` shows them, marked. Sorting: by `starts_at`, soonest first, unknown last. `GET /api/games?sport=&q=&limit=&include_started=` (login required): `sport` and `q` (substring of the title or league, case-insensitive) filter the cached list; `limit` 1 to 500, default 200. The response also carries `sports`, `fetched_at` and `errors`.
- Done when: tests with realistic fixtures for grouping, sorting, started flag, filters, partial failure, cache hit and expiry, parallel limit, a single shared fetch for simultaneous calls, and the settings parsing; and a live check by me of every default series ticker (done once, by hand, with the user's VPN).

### Task 3 (FEAT-...): Research per game
- Alembic migration: on `runs`, rename `market_ticker` to `event_ticker` and `market_title` to `event_title`, with the two indexes renamed to match (`alembic check` must stay clean). No data to convert (development database).
- `MarketInfo` becomes `GameInfo`: `event_ticker`, `title`, `sub_title`, `starts_at`, `outcomes` (labels), `rules` (the `rules_primary` of the first outcome; the game is the same for all of them). The planner and researchers are given the game, its start time and its outcome labels, and still **not** any price.
- `POST /api/runs` takes `{event_ticker}`; the server fetches the event with `get_event` (404 when unknown, 502 on Kalshi problems), builds the `GameInfo`, and keeps every existing guard (one active run per event, run limit, research on).
- Prompts reworded from "market" to "game" and told to consider every listed outcome.
- Done when: the existing run tests pass in their event form, and new tests cover the game description (outcomes present, no price), 404 and the migration.

### Task 4 (FEAT-...): Web app
- The Markets page becomes the games list: sport filter (All, Soccer, Baseball, Tennis, from the response) and a title search, both as plain links and a form (no client-side state); one row per game: title and league, start time in the viewer's time zone (a "Show started games" link shows the hidden ones, marked "Started"), each outcome with its buy and sell price ("Newcastle 43–44¢"), a "Research" button per game (Analyze, In progress, View research, Analyze again, as now).
- A price shows as "–" when bid or ask is missing; the last-trade price is not used.
- Errors per league are listed under the table; the loading state stays.
- Run list and run page use the event title and ticker; text says "game".
- Done when: lint and build pass; against a mock Kalshi in Docker the list shows grouped games with prices and start times, the filter and search work, Analyze starts a run for the game; page width unchanged on every page at 1280 px and 390 px.

### Task 5 (FEAT-...): Documents
- `docs/agent/GRAPHS.md` (game input, outcomes, start time, one run per game), `docs/ARCHITECTURE.md`, `docs/MILESTONES.md`, and `docs/discussion/NOTEPAD.md` (decisions, what changed, what is not verified).

## 5. Order of work and commits

Tasks 1 to 5 in order, one commit each on `feature/sports-games-list`; TODO markers `[ ]` to `[o]` to `[x]` with the completion time in the closing commit.

## 6. Out of scope

Per-outcome research, forecasts per outcome (Milestone 3), the events paging approach, a live odds feed, other sports, ordering by anything but start time, per-user league choices, and any change to sign-in.

## 7. Known limits

- The league list is a setting; a league not on it does not appear until added. The client should confirm the leagues.
- Over a VPN a full refresh of about a dozen series takes about 10 seconds; the first page load after a restart or after the cache expires waits for it (the loading state shows). From the client's network it is likely much faster (unmeasured).
- Games already started are hidden unless asked for (a toggle on the page); Kalshi keeps them open until they settle.
