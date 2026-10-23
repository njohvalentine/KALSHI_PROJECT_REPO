# Spec: update a researched game with the confirmed lineups and late team news (FEAT-20261022-0956)

Working branch: the one checked out, `feature/security-hardening` (base `master`); product work would be cleaner on its own branch, which is the user's call (branches are theirs to direct). From the client's message of 2026-10-22: research should cover "confirmed lineups", and the agent should update "when important information changes" (answer 4: a change in the forecast and the price). Soccer first (answer 3).

## What is there now (verified in `runs.py`, `runner.py`, `graph.py`, `prompts.py`, `sources.py`, `check.py`, and the saved runs)

- **A forecast is made once, hours before the start.** Confirmed soccer lineups are published about an hour before kickoff, so most forecasts are made before they exist. In our 95 saved runs only 21 have any lineup claim (58 of 2,465 claims, 2.4%), and an absence or injury fact is in 152 claims (6%).
- **The planner may or may not plan a lineup angle** ("injuries, suspensions and expected lineups" is one example among several); nothing makes the research ask for confirmed lineups.
- **A repeat run is possible today but wasteful.** "Research again" (`confirm_repeat`) runs the whole pipeline again (planner, three researchers, checking, three forecasters, plain-AI call), about 0.40 USD, and counts as one of the 5 games a day.
- **The researcher format makes a lineup list impossible as written.** The researcher writes at most 10 lines, one fact per line, and may not join several players in one line (`RESEARCHER_INSTRUCTIONS`). A lineup is 22 names. What matters for a forecast is who is **missing** or surprising, not the 22 names, so the question must ask for that.
- **The flow is reusable.** `execute_run` runs the graph, saves findings and cited pages (`save_sources`), then fetches pages, judges claims that have no check yet (`check_run` skips a claim that already has a row), builds the supported claims and runs the forecasters. Scoring already takes the latest forecast before the start for each market and reports the first against the latest forecast of the markets forecast more than once.

## Design

**An update is a new, cheaper run of the same game, linked to the run it updates** (`runs.refresh_of`, a new nullable column; one Alembic migration made with autogenerate).
1. **No planner and one researcher.** The graph gets a mode with a fixed angle per sport instead of the planner. Soccer: "Lineups and late team news": *which regular starters of either team are NOT in the confirmed starting lineup or are out, injured, suspended or doubtful, and what surprise selections or formation changes were announced; give the time each source was published; if the lineups are not published yet, say so in one line*. Baseball: confirmed starting pitchers and lineup cards. Basketball: starters and the injury report status. Tennis: withdrawals, order of play, medical news. Other sports: a general question about the latest team news. Only soccer is tested at first.
2. **The earlier evidence is carried over, not paid for again.** The facts already checked in the run being updated (its findings, their saved pages and their claim checks) are copied into the update run, with the finding indices remapped, and each carried finding gets the label "Earlier research (N hours ago)". Nothing carried is fetched or judged again. The new findings go through the normal fetch, check (the app's strict rule: a lineup or injury claim is supported only if the page shows a time that fits it) and forecast. The forecasters see the earlier facts under their label and the new ones as "Latest check", and the prompt says: *if a later fact contradicts an earlier one about the same thing, trust the later one*.
3. **Expected cost about 0.20 USD** (one researcher, one judge pass, three forecasters, the plain-AI call), against 0.40 for a full run. To be measured on the first updates.
4. **A separate limit.** `RESEARCH_UPDATES_MAX_PER_DAY` (default 5; 0 means no limit), counted over the last 24 hours the same way as the research limit, under the same advisory lock. Updates do not use the 5 game slots, and the game limit counts only runs that are not updates. The setting is passed through `docker-compose.yml` without a default there, listed in `.env.example`, and covered by the compose-settings test.
5. **When an update is allowed:** the run is the latest finished run of its game with a forecast, the game has not started, no run of the game is in progress, OpenAI is configured and the update limit is not reached. Otherwise the endpoint says why (409, 429, 503).
6. **Trigger:** `POST /api/runs/{run_id}/update` (the guard header, login) and a button **"Update with lineups"** on the result page of such a run, with the cost estimate and a note when the game is more than 3 hours away: *lineups are usually published about an hour before the start; an update now will probably find only expected lineups*. No automatic trigger here (watcher: FEAT-20261022-0958).
7. **Before and after on the page.** The update run's page says it is an update of the run from (time), links to it, and shows the earlier probability beside each outcome with the change. The run detail carries `refresh_of` and the earlier probabilities.

**Measurement (nothing is claimed in advance).** The update's own records are scored like any run (the latest forecast before the start is the one that counts, and the earlier one stays on file). `score-records` gets one line for updated games: how many, and the Brier score of the first and of the updated forecast on the same outcomes. An accuracy answer needs about 50 updated games; until then the line says "too few". After the first 20 updates two operational numbers are reported: the share of updates run 45 to 90 minutes before the start that found at least one supported lineup or absence fact, and the cost per update.

## Not done

No automatic update by the watcher or on a price change (FEAT-20261022-0958); no other sport tested; no lineup list of all 22 names; no new market kinds; no change to the flag rule; no change to how a normal run works.

## Risks, stated now

If used on every game it adds about half a run per game; many updates will find only expected lineups if made early; the update replaces the original in scoring (as intended; both stay on file); a carried fact can be out of date, which the label and the "trust the later fact" rule only limit; our record so far shows no edge, and a lineup update may not change that.

## Checks to state at close

Lateral: every place that counts runs for the daily limit (`_insert_run`, the dashboard spend line, the watcher's batch rule) must treat updates the same way; every place that lists "the latest run of a game" (Opportunities, Ranking, the games list) takes the update run, which is the intended newest forecast. Causal depth: the client's request has two needs, timely information and an update when it changes; this item covers the first and the manual trigger of the second, and leaves the automatic trigger to its own item.

## Tests

The migration; the fixed angle per sport and that the planner is not called in update mode; carry-over (findings, pages and checks copied with remapped indices, nothing fetched or judged again, labels set); the forecaster input groups earlier and latest facts and keeps the markers and label protections; eligibility and each refusal (started game, run not latest, run in progress, no OpenAI, update limit); the two limits do not count each other's runs; the endpoint needs login and the guard header; the run detail and page show the earlier probabilities; the `score-records` line on a known set; the compose-settings test for the new setting. A live check on one real game with a mocked clock is not possible, so the first real updates are watched and reported.
