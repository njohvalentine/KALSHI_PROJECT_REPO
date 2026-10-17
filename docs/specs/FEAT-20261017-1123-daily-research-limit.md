# Spec: a hard daily limit on researched games (client priority A)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "I would prefer to begin with 5 researched games per day, with the option to increase". The user approved the nine items on 2026-10-17. This is the first.

## What is there now (read in the code)

- A run starts in `runs.py: start_game_run` for both a person (the Research button) and the watcher. It only checks the number of runs in progress (`MAX_CONCURRENT_RUNS`, 2) and that no run is already active for the game. There is no limit on how many games are researched in a day.
- The only daily limit is `AUTO_RESEARCH_MAX_PER_DAY`, and it counts only automatic runs (`Run.trigger == "auto"`); a person can research without limit.
- A rejected start is a `RunStartError` (429 with a message and `Retry-After`); the Research button shows the message, and the watcher stops for the cycle on 429 (`monitor.py`).

## Design

- **New setting `RESEARCH_MAX_PER_DAY`**, default 5, `0` means no limit. A behaviour knob with a safe default (it only blocks spending), so a code default is fine; the startup log line says the limit (or "off"). Documented in `.env.example` and the run guide. The default is 5 because the client asked to start with 5; an operator who wants more sets it.
- **The day is the last 24 hours** (a rolling window), not a calendar day: the client is in Texas and the server clock is UTC, so a calendar day would reset at the wrong hour. The count is every run created in that window, whoever started it, including re-research of the same game and runs that failed (a failed run may still have spent credit). A run that is refused for any reason before it is inserted is not counted.
- **No overshoot:** counting and inserting are one database step. `_insert_run` takes a transaction-level advisory lock (`pg_advisory_xact_lock`) on a fixed number, counts the runs of the last 24 hours, and inserts only if the count is below the limit; otherwise it raises a new `DailyLimitReached` error. So two parallel presses cannot both take the last slot (checking first and inserting later would allow that).
- **Message:** the start is refused with HTTP 429 and the text "The daily research limit is reached: N games in the last 24 hours. The next slot opens at HH:MM (UTC), when the oldest of them is 24 hours old. The limit is set by RESEARCH_MAX_PER_DAY." with `Retry-After` in seconds. The Research button already shows the message; the watcher already stops its cycle on 429, so automatic research respects the limit with no change.
- **Dashboard:** `/api/dashboard` gets `research_window: {used, limit}` and the "Research spend" card's line adds "N of 5 games researched in the last 24 hours" (nothing when the limit is off).
- Existing tests that start many runs set `RESEARCH_MAX_PER_DAY=0`, and new tests set a small limit.

## Not done

No change to the concurrent-run limit, no per-sport limit, no money limit (a limit in dollars could come later; the game count is what the client asked for), no calendar-day option.

## Tests

Backend: the limit refuses the sixth start with 429 and the message; a run older than 24 hours does not count; a failed run counts; the limit `0` allows any number; two starts at the same time with one slot left give exactly one run (the lock); the watcher's automatic start is refused by the same limit; the Dashboard shows used and limit; the config parser rejects a negative or non-number value with a clear message. Frontend: lint, build, the browser tests and a screenshot of the Dashboard card.

## Checks to state at close

Lateral spread: every route that starts a run goes through `start_game_run` (the endpoint and the watcher); I search for any other insert of a `Run` (the replay tool and tests) and state the result. Causal depth: the need is that the credit cannot be spent by mistake; the limit covers a person, the watcher, re-research and parallel presses, and does not depend on the clock of the viewer.
