# Spec: accuracy and paper profit by sport and by kind of market (client priority D)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "Track prediction accuracy, actual results, simulated profitability and performance by sport and market type". Approved by the user on 2026-10-17 as the sixth item (the bookmaker comparison part of D was done in item C).

## What is there now (read in `research/records.py`, `dashboard.py`, the Dashboard and Results pages)

- `score_records` already computes, per sport, per league, per kind of market and per amount of evidence: games, outcomes, our Brier score, the scores of ours, the plain AI and Kalshi on the same outcomes, and the paper result of buying the chosen side at the ask (`paper_all`: bets, won, average and total). The flagged bets are summed only over all games (`paper_flagged`), not per group.
- The Dashboard shows only a bar chart by sport (ours against Kalshi) and no paper result; it does not show kinds of market at all. The Results page shows three cards and the simulated orders; no breakdown. The command `score-records` prints the numbers; the app does not.

## Design

- **Backend:** `_group_scores` also returns `paper_flagged` per group (the same `_paper` function over the flagged rows), so a sport or a kind shows how its flagged bets did. `/api/dashboard` returns `by_sport` (extended) and a new `by_kind`, each row: the group, games, outcomes, the three scores on the same outcomes, and the paper result of all chosen sides and of the flagged ones (bets, won, average and total result per contract). Nothing is recalculated: it is the same code as `score-records`.
- **One shared table component** (`components/group-table.tsx`) used twice with two column sets:
  - Dashboard, "Accuracy by sport and by kind of market": group, games, ours, plain AI, Kalshi (Brier score, lower is better), and a plain mark where ours is better than Kalshi's (never colour alone).
  - Results, "Simulated result by sport and by kind of market": group, bets, won, average result per contract after fees, total, and the flagged bets' won out of bets and average.
- **Cautions in the numbers:** a group with fewer than 5 games says "too few games to read" and has no mark; a paper average over fewer than 30 bets says "too few to read", as the cards do. A footnote says the bets are simulated at the ask with fees, one contract each, and that the markets of one game move together.
- The kinds read "Who wins", "Total goals, runs or points", "Both teams to score", "Margin of victory" (the labels already used on the run page). Evidence level is not added (the report has it; it was not asked for).
- Documented in the run guide (Dashboard and Results lines).

## Not done

No league breakdown on the pages (the report and `score-records` have it), no date filter, no chart for the profit, no change to how the paper result is calculated.

## Tests

Backend: `paper_flagged` per group equals `_paper` over the flagged rows of that group (one group with flagged rows, one without); the dashboard returns `by_kind` with one row per kind present, `by_sport` extended, and the paper fields; a group with fewer than 5 games is marked; an empty database returns empty lists. Frontend: lint, build, the browser tests (the Dashboard and Results tests also check the two table headings) and desktop and phone screenshots.

## Checks to state at close

Lateral spread: the Dashboard, the Results page and `score-records` all read `score_records`, so their numbers agree; I compare the Dashboard rows with the command's output. Causal depth: the request has four parts (accuracy, actual results, simulated profit, by sport and kind); the first and last were half there, the profit by group and the kinds were missing from the app.
