# Spec: replay of the forecasting step on frozen evidence (`replay-forecasts`)

Branch `feature/sports-games-list` (base `master`). For approval; nothing is built yet. The synthesis was approved by the user on 2026-10-14 ("yes, go ahead").

## Why (the need behind the request)

Every idea about the forecasts (a different model or prompt, more forecasters, other flag limits) can only be tested on new games, one day at a time, because a fresh run on a finished game can find its result through the live web search. We want to try several ideas **now**, on the games already finished, without that leak, and use the games still to finish as an untouched test set. A replay is only a way to produce candidates faster; the answer to "does the system find real opportunities" still comes from games it did not see.

## What is frozen and what is not (verified 2026-10-14)

Saved before the game and never changed, so a replay cannot leak a result:
- **The game as the forecasters saw it** (outcomes, short names, companion market groups with lines, rules, start time): in the LangGraph checkpoint of the run (`thread_id` = run id), read with the existing `open_checkpointer`. Verified on a real run (Dallas vs Seattle): `event_ticker`, `outcomes`, `outcome_tickers`, `outcome_names`, `groups`, `rules`, `starts_at` all present.
- **The evidence:** `runs.result.findings` plus `claim_checks` give exactly the claims that went to the forecasters (`supported_claims(findings, checks)`, the function the run uses).
- **The market of that moment, the plain-AI call and the original forecast:** `outcome_records` (yes bid and ask, no ask, sizes, fee type and multiplier, baseline probability, our probability), and `runs.prediction`.
- **The day the run was made:** `runs.created_at` (the forecaster prompt carries today's date, so a replay uses the run's date, not today's).
- **The result:** `outcome_records.resolved_yes`, filled by `resolve-records`.

Not frozen and not replayable: the research step itself (it searches the live web) and games without a saved checkpoint.

## Design

1. **Command** `replay-forecasts` with: `--created-after`/`--created-before` (which runs), `--forecaster-count`, `--forecaster-model`, `--forecaster-effort` (overrides of the settings), `--rules-only` (no model call: replay only the flag rule on the original forecasts, free), `--edge-min`, `--min-supported-claims`, `--min-research-shift`, `--edge-plausible-max`, `--min-ask-size` (flag limits), `--tune-until DATETIME` (see 5), `--yes`.
2. **What it re-runs.** For each eligible run (done, has a checkpoint, claims saved, all its records resolved): rebuild the `GameInfo` from the checkpoint; take the supported claims; call `run_forecasters` with the chosen settings and a forecaster model whose date is fixed to the run's date (`OpenAIForecastModel(settings, today=...)`, a new optional argument, default unchanged); build the prediction with the existing `build_prediction`; then judge every market with the existing `compare_outcome` using the **stored** prices (rebuilt from the record into the dict the function reads) and the stored baseline.
3. **What it prints.** Per setting set: the number of games and outcomes; Brier of the replay, of the original forecast, of the plain AI and of Kalshi on the same outcomes (winner markets and all markets); how many markets are flagged and what buying the chosen side at the ask would have paid (as `score-records` does, same fee formula). Original and replay side by side, so a change is visible. No verdict is printed.
4. **Cost control.** Before any model call it prints the number of games, the forecaster calls (games x count) and an estimate (about 0.10 USD a game at the defaults: each forecaster about 0.03); it calls the model only with `--yes`. `--rules-only` needs no `--yes`. It stops with a clear message if a run has no checkpoint (the game is skipped and counted, never rebuilt from guesses).
5. **Held-back test set.** `--tune-until DATETIME`: runs created after it are left out of every number and counted ("12 later games held back as the test set"); only a run with `--final` (and no `--tune-until`) includes them. The person decides the candidate settings on the early games, writes them down, then runs `--final` once. The command cannot stop someone from peeking, but it makes peeking explicit.
6. **Nothing is written.** No row of `outcome_records`, `forecasts`, `runs` or any other table changes; the replay is printed only. (A test checks table counts before and after.) Model usage is logged with its cost.
7. **Risks stated in the output:** tuning on a few games fits noise; the original and replayed forecasts differ partly by chance because models are not deterministic, so each setting set is run once and the differences are small unless the settings differ a lot; the replay measures the forecasting step only.

## Not done

- A replay of the research or checking steps (they need the live web or the judge; a separate item if wanted).
- Saving replays in the database or showing them on a web page.
- Automatic search for the best settings (that would overfit); the person chooses the candidates.

## Tests

Scoring of a replay on a hand-worked set; the flag replay equals `compare_outcome` on the stored prices and baseline, and a changed limit changes the flag; a fake forecaster receives the frozen game, the same claims `supported_claims` gives and the run's date, not today's; the settings overrides reach the forecaster calls (count, model, effort); no `--yes` means no model call and a printed estimate; `--rules-only` makes no model call; `--tune-until` leaves later runs out and says how many; a run without a checkpoint is skipped and counted; tables are unchanged after a replay.

## Checks to state at close

Lateral spread: every input of the forecasting step is either read from a frozen place or named as not replayable (the date, the game, the claims, the prices, the baseline); no other code path writes records from a replay. Causal depth: the need is "test ideas without waiting and without leaking"; the freeze covers leaks of results, the held-back set covers overfitting, and the stated risk covers noise from non-deterministic models; the first cannot replace new games.
