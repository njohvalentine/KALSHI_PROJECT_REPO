# Replay plan, written before any result was looked at (2026-10-14)

Written and committed **before** running the candidates below, so the choices cannot be adjusted after seeing the scores.

## Sets

- **Tuning set:** games whose run was made up to `2026-10-14T00:00:00Z` and that have finished (15 games on 2026-10-14 morning; `--tune-until 2026-10-14T00:00:00`).
- **Test set:** games whose run was made after that moment (the 23 games researched on 2026-10-14). They finish tonight and tomorrow. Not scored, not replayed with a model, until the decision below is fixed; `--final` is run once.

## Candidates (fixed now)

| Id | What changes | Why this one | Cost on the tuning set |
|---|---|---|---|
| C0 | nothing (3 forecasters, gpt-5.4, medium effort, current flag rule) | measures how far a replay differs from the original by chance alone (the models are not deterministic): the noise floor every other difference is judged against | about 1 to 2 USD |
| C1 | 5 forecasters instead of 3 | the median of more forecasts should be steadier | about 2 to 3 USD |
| C2 | reasoning effort high instead of medium | more thinking per forecast, the usual first thing to try | about 3 to 5 USD |
| R1 | flag rule: `--edge-min 0.08` | the flag may be too loose | free (rules only) |
| R2 | flag rule: `--min-supported-claims 8` | more evidence before flagging | free (rules only) |

Not tried, on purpose: any other model (price and unknown quality), more candidates (each extra candidate raises the chance that one looks good by luck), automatic search over settings.

## Decision rule (fixed now)

A candidate is **adopted for further testing** only if, against C0 on the same games, the all-markets Brier score is lower by **at least 0.005** on the tuning set. Only adopted candidates are run on the test set (once, with `--final`). It is **kept** only if it also beats the current setting on the test set by at least 0.005 on the all-markets Brier score. For R1 and R2 (flag rules) the Brier score does not change; they are judged on the paper result of the flagged markets and on how many markets they flag, and are only a hint: a flag rule changed on 15 games with 5 flagged bets cannot be proven on this sample, so R1 and R2 are reported, not adopted, until there are enough flagged bets (at least 30) on finished games.

Noise: if C0 differs from the original by more than 0.005 on the tuning set, that size of difference counts as noise, and a candidate must beat C0 by more than the C0-versus-original gap, not only by 0.005.

## What this can and cannot show

A few games and a handful of candidates: any gain below the noise floor is not a finding. The replay does not test the research step. Whatever the result, the question "does the system find real opportunities" is answered by games it did not see: the test set and the days after.
