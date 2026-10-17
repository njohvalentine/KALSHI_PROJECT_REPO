# Spec: ask before paying twice for the same game (client priority E)

Branch `feature/sports-games-list` (base `master`). The client asked on 2026-10-16 for "caching to prevent unnecessary repeat research charges". Approved by the user on 2026-10-17 as the second item.

## What is there now (read in the code)

- `runs.py: start_game_run` refuses a start only when a run for the game is already queued or running (a database rule, answered with 409 and the active run's id, which the Research button follows to that run). A game that was researched an hour ago can be researched again at once, for a full run (about 0.43 US dollars), with no warning.
- The button says "Research again" on a game with a finished run, and the watcher's automatic research skips games researched in the last `AUTO_RESEARCH_MIN_GAP_HOURS` (12), but that skip lives in the watcher, not in the start itself.
- The forecast is treated as fresh for `OPPORTUNITY_MAX_AGE_HOURS` (12): older ones are shown greyed and never flagged.

## Design

- **Server side, so no screen can bypass it:** `start_game_run` looks for the latest finished run of the game made less than `OPPORTUNITY_MAX_AGE_HOURS` ago (no new setting: the same time after which the app itself calls a forecast old). If there is one and the request does not say `confirm_repeat: true`, nothing is started and the answer is HTTP 409 with `code: "recently_researched"`, the age of that run in hours, what it cost, and the sentence "This game was researched N hours ago for $X, and its forecast is still fresh. A new run costs about the same and counts against today's limit. Prices may have moved, which you can see on the Opportunities page without a new run." It has no `run_id`, so the existing "follow the active run" behaviour is untouched.
- **A confirmed repeat** (`confirm_repeat: true`) goes on exactly as today (and still meets the daily limit).
- **The watcher never confirms:** automatic starts go through the same guard and are refused, so the rule no longer depends on the watcher's own filter; the watcher logs the refusal as it does other refusals.
- **A failed or unfinished previous run does not trigger it** (it has no forecast); a run older than the freshness time does not either.
- **The button:** on that 409 the Research button shows the sentence with "Research again anyway" and "Cancel"; confirming sends the same request with `confirm_repeat: true`. Without scripts nothing changes for a first research.
- Documented in the run guide's Limits paragraph.

## Not done

No cache of page texts or claim checks across runs (the same page cited in two runs is read twice; measured cost of that is small next to the research calls, and it would need a decision on how long a saved page stays valid; it can be a later item). No "warn but allow" for the watcher.

## Tests

Backend: a second run within the freshness time is refused with the code, the age and the cost; the same request with `confirm_repeat` is accepted; a run older than the time, or a failed run, does not trigger it; the watcher's call (`start_game_run` with trigger auto) is refused by the guard; the confirmed repeat still meets the daily limit. Frontend: lint, build, and a browser test that mocks the 409 answer on the Games page, checks the sentence and the two buttons, and that "Research again anyway" sends `confirm_repeat: true`.

## Checks to state at close

Lateral spread: every start goes through `start_game_run` (the button, the watcher); the Opportunities and Games buttons share the one `AnalyzeButton`. Causal depth: the cost came from three causes, a button that allows repeats without a word, a rule that lived only in the watcher, and no sign of what the last run cost; the guard states the cost, is enforced on the server and covers every caller.
