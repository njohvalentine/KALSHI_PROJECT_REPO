# Spec: the Milestone 4 accuracy report

Branch `feature/sports-games-list` (base `master`). For approval; nothing is written yet except this spec. Item `FEAT-20261014-1127`. Documentation only: no code, no new dependency, no model calls (no money spent).

## Why

The client's priority is to "establish whether the application can consistently identify genuine opportunities". Milestone 4 promised a written accuracy report. We now have 61 finished games (483 outcomes) and the replay results, so the report can be written on real numbers.

## Design

- **File:** `docs/ACCURACY-REPORT-2026-10-15.md`, plain English, for the client and for us. A short summary first (the answer), then the details.
- **Numbers:** taken only from `score-records` (re-run once, at writing time, after the last games of 2026-10-15 are resolved with `resolve-records`; the date and game count are printed in the report). I will not type numbers from memory.
- **Contents:**
  1. The answer in five lines: ours 0.194, plain AI 0.197, Kalshi 0.175 (or the re-run values); no sign of an edge yet; too few games for a verdict.
  2. What was measured and how (Brier score in plain words, "lower is better"; what "flagged" means; fees; the latest forecast before the start of each market).
  3. Scores by sport, league, evidence level and kind of market (winner, totals, spread, both-score), each with its number of games.
  4. Flagged bets: count, wins, average result per contract, with the plain statement that fewer than 30 bets say nothing about profit or loss and results swing about ±15¢ between draws.
  5. The replay experiments: rules written before running, what was tried (5 forecasters, high effort, flag-rule variants), tuning set against held-back test set, the decision to keep the current settings, and the real cost ($6.82 against the $4–5 estimate).
  6. Why Kalshi is hard to beat (its price already holds public information; our research adds little over a plain AI; the forecasters are copies of one model; thin evidence from blocked pages; fees). Where research does help: tennis (own 0.233, plain AI 0.261, Kalshi 0.222, still behind Kalshi).
  7. The flag limits: the placeholder values (`EDGE_MIN` 0.05, `MIN_SUPPORTED_CLAIMS` 5, `EDGE_PLAUSIBLE_MAX` 0.15) with what the results say about each. If the results do not support changing them, the report says so and keeps them. It will not pick values that look good on the same games (the replay rules already warn about that).
  8. Caveats: modest sample; the markets of one game move together (so 483 outcomes are about 61 independent games); sports with fewer than 20 games are "not yet measured"; no real orders were ever placed.
  9. Options for the next step, not decided (anchor on the market price, bookmaker consensus, focus on tennis, structural edges from historical data, use as a research assistant), with the recommendation that Milestone 7 (real orders) stays a no-go for now.
- **Docs:** `docs/MILESTONES.md` Milestone 4 links to the report; `TODO.md` item closed in the same commit.

## Not done

No changes to the flag limits in code or `.env` (those need your decision after reading the report). No new experiments. No client message (you send those; I can draft a short one after).

## Checks to state at close

Lateral spread: the numbers in `MILESTONES.md`, `NOTEPAD.md` and the project memory are compared with the report and corrected where they differ. Causal depth: the need is an honest answer to "can it find real opportunities"; the report answers that on scores, on flagged bets and on the replays, not on one of them.
