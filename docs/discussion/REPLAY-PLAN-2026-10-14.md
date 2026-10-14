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

## Results on the tuning set (15 finished games, 62 outcomes; run 2026-10-14, after the plan was committed as 4a35091)

All-markets Brier (lower is better) on the 61 outcomes that have a plain-AI call and a two-sided price; original forecast 0.1924, plain AI 0.2222, Kalshi 0.1536.

| Id | All markets | Winner markets only | Flagged markets (paper result per contract) | Model calls, cost |
|---|---|---|---|---|
| C0 (current settings) | 0.1918 | 0.1930 | 4 (-0.057) | 45, 0.63 USD |
| C1 (5 forecasters) | **0.1791** | 0.1924 | 7 (+0.136) | 75, 0.90 USD |
| C2 (high effort) | 0.1880 | 0.1952 | 4 (+0.053) | 44, 0.89 USD |
| R0 current flag rule, original forecasts | 0.1924 | 0.2025 | 5 (+0.084) | free |
| R1 `--edge-min 0.08` | same | same | 2 (-0.171) | free |
| R2 `--min-supported-claims 8` | same | same | 4 (+0.234) | free |

## Decision rule applied

- **Noise floor:** C0 against the original forecast differs by 0.0006 on the all-markets score, below the 0.005 threshold, so the threshold stays 0.005. (On winner markets alone C0 differs from the original by 0.0095: replays of the same settings move that much on 33 outcomes.)
- **C1:** better than C0 by 0.0127 on all markets: **adopted for the test set**. On winner markets alone it is level with C0 (0.1924 against 0.1930), so the gain is in the other kinds of market (total, spread, both teams to score), not in picking winners.
- **C2:** better than C0 by 0.0038, below 0.005: **not adopted**, and it cost more.
- **R1 and R2:** reported, not adopted, as the plan says (2 and 4 flagged bets).

## What the flagged results show

The same flag rule gave 4 flagged bets averaging -0.057 per contract with C0, 7 bets averaging +0.136 with C1, 4 bets averaging +0.053 with C2, and 5 bets averaging +0.084 on the original forecasts. These all use the same rule on the same games: the results move by 0.15 to 0.2 dollars per contract between draws of the forecasters. With 4 to 7 bets the flagged result is noise, and none of these numbers supports or rejects the flag.

## Next

Once the 23 games researched on 2026-10-14 have finished and `resolve-records` has run: `replay-forecasts --tune-until 2026-10-14T00:00:00 --final --yes` for C0, and the same with `--forecaster-count 5` for C1, each once. C1 is kept only if it beats C0 on the test set by at least 0.005 on the all-markets score.
