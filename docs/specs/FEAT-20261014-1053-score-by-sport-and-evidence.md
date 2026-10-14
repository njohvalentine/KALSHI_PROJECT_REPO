# Spec: scores per sport, league and amount of evidence (FEAT-20261014-1053)

Branch `feature/sports-games-list` (base `master`). For approval; nothing here is built yet.

## Why (the need behind the request)

The client's priority is to learn whether the system can consistently find real opportunities. The first scores (15 games, 2026-10-14) show one number for everything: ours 0.192, plain AI 0.222, Kalshi 0.154. A single number can hide the answer: one sport or one level of evidence may be good while another sinks the average, and the system's own flag already depends on evidence (at least 5 supported claims). The two tennis runs of 2026-10-14 had 0 or 1 supported claims, so their forecasts are close to a plain AI guess. We need the scores split the way the decisions are: keep or drop a sport, trust a forecast or not by how much evidence it has.

## Verified in the code

- `score_records` (`backend/app/research/records.py`) already groups the scored outcomes `used` by `market_kind` through `_kind_scores`, which computes the outcome and game counts, Brier of ours, and on the records that have all three (ours, plain AI, Kalshi middle) the three Brier scores and the paper result of the chosen side.
- A record has `evidence` and `supported_claims` but no sport. The game's series is the first part of its `event_ticker` (`KXMLSGAME-26OCT14MIANYC` → `KXMLSGAME`), and the settings already map each series to a sport and league (`SPORTS_SERIES`, `Sport:SERIES:League`). Records of companion markets (total, both teams to score, spread) keep the **game's** event ticker, so the game's series gives the sport for all its records.
- `score_records(engine, since)` has no access to settings; the command (`app/cli.py`) has them.

## Design

- `_kind_scores` becomes `_group_scores(used, key)` (same output per group) and is used for four groupings: kind of market (as now), sport, league, evidence bucket. No change to the database.
- Sport and league come from the series of the record's `event_ticker` through a map built from `settings.sports_series`; a series that is not in the map is grouped as "unknown" and shown. `score_records(engine, since, series=None)` takes the map; without it the sport and league groups are left out (the existing tests and callers keep working).
- Evidence buckets: "none" (no supported claim), "1 to 4 supported claims", "5 or more" (the flag needs at least `MIN_SUPPORTED_CLAIMS`, 5; the bucket edge is the constant, not a copy).
- Each group prints the same line as the kind lines now: outcomes, games, Brier ours, then on the records that have all three: ours, plain AI, Kalshi, and the paper result of the chosen side. Groups with fewer than 5 games say "too few games" in the line so nobody reads a number built on two games.
- A game with several markets counts once in the games column of every group it belongs to; the outcomes column counts markets, which move together. The existing footnote about this stays.
- The headline, the exclusion rules and the 30 game threshold do not change.

## Not changed

No web page for the scores (the command is the report until Milestone 4's report, which will use these numbers). No new setting. No change to how forecasts are made or flagged: this only reads results. If tennis turns out weak, dropping or keeping it is a separate decision for you and the client.

## Tests

Hand-worked set with two sports and two evidence levels (extends `test_scores_on_a_hand_worked_set` style): the per-sport, per-league and per-bucket numbers equal the numbers computed by hand; an unknown series is shown as "unknown"; without a series map the groups are absent; the printed report contains the new sections and the "too few games" note; the existing tests still pass.

## Checks to state at close

Lateral spread: every consumer of `score_records` output (the command, `format_report`, tests; nothing else reads it). Causal depth: the need is "see what carries the result"; sport, league and evidence are three views of it, and kind of market already existed; one more factor, the number of forecasters that stayed valid, is already near-constant (3) so it is not split.
