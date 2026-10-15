# Spec: discover all sports markets on Kalshi, with the NBA (FEAT-20261015-0917)

Branch `feature/sports-games-list` (base `master`). For approval; nothing is changed yet. Requested by the client on 2026-10-14 ("I recommend that your agent discover all currently available sports markets through Kalshi, instead of maintaining a fixed list of leagues"; basketball means the NBA). Replaces WISH-20261014-0912.

## Why (the need behind the request)

A fixed list of 15 series means anything not on it is invisible: other soccer leagues, the NBA, hockey, football, cricket, MMA and so on, and the list needs a person to edit it whenever a league starts or ends. The client wants to see and research whatever Kalshi offers. The honest limit is that our forecasts have not shown an edge even in the three sports we know (51 games, 2026-10-15), so a new sport must be marked as not yet measured.

## What Kalshi offers (read 2026-10-15, read-only)

- `GET /series?category=Sports`: **3,978 series**, each with `tags` (the sport: Soccer 1,471, Basketball 669, Football 593, Baseball 234, Tennis 143, Esports 135, Golf 126, Hockey 99, Motorsport 65, Cricket 56, MMA 54, ...), `title`, `fee_type`, `fee_multiplier`. 363 tickers end in GAME or MATCH. Too many to ask one by one.
- `GET /milestones?category=Sports&minimum_start_date=...` (already used for kickoff times): **3,664 milestones in the last 48 hours, from 528 series in 19 types** (soccer_tournament_multi_leg 1,100; tennis singles 971 and doubles 379; football_game 262; basketball_game 243; esports_match 138; table_tennis_match 125; hockey_tournament 114; cricket_match 99; hockey_match 64; mma_match 42; darts_match 38; volleyball_match 31; boxing_match 21; baseball_game 16; golf, racing, other). Each has `primary_event_tickers` (the game's main event) and a `type`. **In the next 3 days: 1,339 milestones from 382 series.**
- NBA, read live: `KXNBAGAME-26OCT14DENLAC` is a two-outcome, mutually exclusive winner event; its companions follow the same ticker rule as soccer and baseball: `KXNBASPREAD-...` (25 markets, "Los Angeles C wins by over 17.5 points", not exclusive) and `KXNBATOTAL-...` (21 markets, "Over 205.5 points"). The series fee is `quadratic_with_maker_fees`, multiplier 1.

## Verified in the code

- `backend/app/games.py`: the games list comes from the series in `SPORTS_SERIES`; each series is fetched in parallel (`SPORTS_FETCH_CONCURRENCY`, 6) and the result is cached 60 seconds. The code's own note says fetching everything is far too slow. The list of 15 series is `DEFAULT_SPORTS_SERIES` in `config.py`.
- `backend/app/research/markets.py`: companion markets exist only for `Soccer` and `Baseball` (a table by sport name); a companion ticker is built from a series ending in `GAME`; another sport gets no companions and no error. Tennis (series ending in `MATCH`) has none.
- `backend/app/research/prompts.py` says "The games are usually soccer, baseball or tennis" and lists angles for those. `GameInfo.sums_to_one` takes Kalshi's mutually-exclusive flag, so two- and three-outcome winner events are already handled by the data, not by sport.
- Scoring groups by sport and league through the `SPORTS_SERIES` map (`score_records(..., series=...)`); records have no sport column.
- The watcher alerts for any researched game, and automatic research (off by default) picks games itself.

## Design

1. **Discovery from milestones, not from series.** A game is a milestone whose `primary_event_tickers` event is a winner event of a series tagged with a sport. The series list (`GET /series?category=Sports`) is read once a day and cached; it gives the sport (the first tag) and a league label (the series title without " Game" or " Match") and the fee. Milestone types that are not single games (`soccer_tournament_multi_leg`, `hockey_tournament`, `golf_tournament`, `racing_tournament`, `one_off_milestone`) are skipped: they are tournaments or futures, not a match with two or three outcomes.
2. **Load by sport, not everything at once.** The Games page gets the sports and leagues, with the number of upcoming games, from the milestones alone (already fetched for kickoff times, no extra calls). The prices and outcomes of a game's event are fetched only for the sport the person picks (as the sport filter already exists), with the same 10-minute cache and the existing concurrency; the first page shown is Soccer, Baseball and Tennis, as today. This keeps one page load to the tens of series of one sport, not 382.
3. **`SPORTS_SERIES` stays, with a new meaning.** It becomes the list of **measured** series (the 15 we have scores for): the watcher's alerts and the automatic research and the daily batch use them. `SPORTS_DISCOVERY=true` (new, default on) adds every other sport to the Games page; `false` gives today's behaviour exactly. `SPORTS_EXCLUDE_TAGS` (new) names sport tags that are left out of discovery; default `Esports,Video games,4th of July,Other` (not sports in the usual sense; the person can change it). If discovery fails (Kalshi error), the page says so in words and shows the configured 15 series from cache; no silent fallback.
4. **"Not yet measured".** A sport counts as measured when at least `MEASURED_MIN_GAMES` (new, default 20) of its games have scored records. A game of a sport below that gets a plain badge "Sport not yet measured: no scored games" on the Games, Opportunities and result pages, and its "worth a look" flag and its Telegram alert carry the words "this sport has no scored results yet". To count games per sport from records, `outcome_records` gets two nullable columns, `sport` and `league`, filled when a record is made and filled once for the existing records from the `SPORTS_SERIES` map (a migration). `score-records` groups by those columns, with the map as the fallback for any record without them.
5. **Research for any sport.** The prompts are made sport-neutral ("the games are of any sport; use angles that fit the sport: injuries and expected lineups or starters, form, rest and travel, head-to-head, venue, schedule load") with the specific lines for soccer, baseball and tennis kept and basketball added (back-to-back games, minutes and rotation, pace). Companion markets: `Basketball` gets `total` and `spread` (the NBA ones above); every other new sport gets the winner market only, with a note "no extra markets are mapped for this sport" (never guessed). An event that is not a two- or three-outcome mutually exclusive winner is listed but cannot be researched yet: "unusual market structure" (a named refusal, not a guess).
6. **Cost control unchanged.** Research stays a button. Automatic research and the daily batch use only the measured series (`SPORTS_SERIES`) unless a person picks a game by hand. The watcher keeps watching what was researched.
7. **NBA specifics.** The NBA is discovered like any sport; its 46 extra markets (21 totals, 25 spreads) make the forecaster prompt and answer longer than for soccer, so one run costs somewhat more; the first NBA runs report their real cost. The regular season starts later in October; preseason games are open now.

## Not done

Futures and props (outright winners, player markets, tournament winners); sports whose games have no milestone (they are not listed, as kickoff times come from milestones); extra markets for sports other than the NBA (each needs its tickers read live first); any claim that the forecasts work in a new sport.

## Tests

Discovery from a fake milestones page and a fake series list: a basketball game appears with its sport, league and fee; tournament types and excluded tags are left out; a series that is not in the list is skipped with a reason; with `SPORTS_DISCOVERY=false` the list is exactly the configured one; a Kalshi error gives the named message and the cached configured list. The counts per sport come from milestones with no event fetch; selecting a sport fetches only its series. Companions for the NBA are found by the same rule (fake events); another sport gets none and a note. The "not yet measured" badge and the flag wording appear below the threshold and not above it (hand-built records); the migration fills `sport` and `league` for old records; `score-records` groups by the columns. The prompts contain the sport-neutral text and keep the old lines. An unusual market structure is refused with a message. Playwright: the sport filter lists more than the three sports and a not-yet-measured badge shows.

## Checks to state at close

Lateral spread: every place that reads `SPORTS_SERIES` or assumes three sports (games list, scoring, the watcher, automatic research, the daily batch, prompts, companions, the Games page filter, the RUNBOOK). Causal depth: the client's need is "see and research anything Kalshi lists"; the milestone-based discovery gives the list, the per-sport loading keeps it fast, the badge keeps us honest that nothing there is measured, and the sport-neutral prompts let a run work at all.

## Open choices for the user (the spec follows the first option of each)

1. Default exclusion of Esports, Video games, 4th of July and Other (change with `SPORTS_EXCLUDE_TAGS`).
2. `MEASURED_MIN_GAMES` default 20.
3. `SPORTS_DISCOVERY` default on (the client asked for it); the `.env` value is the user's.
