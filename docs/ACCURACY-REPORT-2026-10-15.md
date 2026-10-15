# Accuracy report (Milestone 4), 2026-10-15

Numbers are from `score-records` run on 2026-10-15 at about 06:35 UTC, after `resolve-records`: **62 finished games, 485 outcomes**. 62 outcomes (8 games, started today) are not finished yet and are left out. The replay numbers are from `docs/discussion/REPLAY-PLAN-2026-10-14.md`. No real order was ever placed; everything here is a paper result.

## The answer

- On 62 finished games the system's probabilities are **not better than Kalshi's own price**. Brier score (lower is better), on the 481 outcomes that have all three: **ours 0.1945, plain AI with no research 0.1970, Kalshi 0.1755**.
- Our research adds almost nothing over the plain AI (0.0025 better, which is inside the noise). Kalshi is clearly better than both (0.019 lower).
- The first 15 games looked good (ours 0.192 against plain AI 0.222). The lead disappeared as more games finished. That is why the early result must not be trusted.
- **No sign of an edge yet.** With 62 games this is not a final verdict either way, but nothing so far points to one.
- Buying the side we chose at the ask price would have lost on average 6.3¢ per contract (485 bets, 194 won). The 35 bets that were flagged "worth a look" lost 12.8¢ on average (13 won). 35 bets are too few to say the flag loses; they do not show that it wins.

## What was measured

- Every researched game saves, before it starts, our probability for each market, a plain AI probability with no research, and Kalshi's price (middle of bid and ask). When the game ends we record who won.
- The **Brier score** is the average of (probability minus result)², where the result is 1 for yes and 0 for no. 0.25 is what always saying 50% gives. Lower is better.
- Only the latest forecast made before the start is used for each market.
- "Chosen side at the ask" means buying the side we gave the higher probability at the price you would pay now (the ask), and holding to the end. It includes no fees; fees make it worse.
- "Flagged" is the rule that says a market is worth a look: gap to the price of at least 5¢ after fees, at least 5 confirmed claims, and a gap that is not so big (15¢) that it is more likely a mistake than an edge.

## Scores by sport, league and evidence

Ours / plain AI / Kalshi, on the outcomes that have all three. Games in brackets.

| Group | Ours | Plain AI | Kalshi | Reading |
|---|---|---|---|---|
| Soccer (28) | 0.1872 | 0.1850 | 0.1643 | research does not help; Kalshi clearly better |
| Tennis (29) | 0.2359 | 0.2618 | 0.2244 | the only place research helps over plain AI; Kalshi still better |
| Baseball (5) | 0.1984 | 0.2056 | 0.1933 | too few games |
| MLS (15) | 0.1666 | 0.1670 | 0.1527 | |
| Champions League (13) | 0.2165 | 0.2104 | 0.1808 | worst for us: −17¢ per contract on the chosen side |
| ATP Challenger (11) | 0.2752 | 0.2649 | 0.2424 | |
| WTA (7) | 0.2895 | 0.3401 | 0.3652 | ours and plain AI beat Kalshi on 14 outcomes; too few to rely on |
| WTA Challenger (8) | 0.1334 | 0.2001 | 0.0937 | |
| ATP, MLB, KBO, NPB | | | | fewer than 5 games each, not read |

- **Kind of market** (the games are the same, so the groups overlap): winner, 62 games: 0.2146 / 0.2206 / 0.1993. Total points or goals, 30 games: 0.1963 / 0.1996 / 0.1742, the worst for the chosen side (−10.6¢). Spread, 30 games: 0.1556 / 0.1528 / 0.1361. Both teams to score, 25 games: 0.2487 / 0.2485 / 0.2321.
- **Confirmed evidence:** games with 5 or more confirmed claims (45 games): 0.1925 / 0.1929 / 0.1737. With 1 to 4 (11 games): 0.2090 / 0.2342 / 0.1856. With none (6 games): 0.2236 / 0.2365 / 0.2083. More evidence did not give a clearer advantage over plain AI; the group with 1 to 4 claims is small.
- **Bookmakers:** the bookmaker benchmark was switched off, so no scored outcome has a bookmaker price. We cannot say how we compare with the bookmakers.
- Markets forecast more than once: 6; too few to say whether a second forecast helps.

## Flagged bets

- 35 flagged bets, 13 won, average −12.8¢ per contract, total −$4.47 on 1 contract each.
- Below about 30 bets (and these bets sit in a handful of games that move together) the result swings by roughly ±15¢ from one replay of the same games to the next, so it is noise. The right statement is "no sign yet that flagged bets win".

## The replay experiments

- Rules and candidates were written and committed **before** running anything (`docs/discussion/REPLAY-PLAN-2026-10-14.md`): the current settings (3 forecasters, medium effort), 5 forecasters, high effort, and two stricter flag rules. A candidate counted only if it beat the current settings by at least 0.005 on the tuning games, and was kept only if the gain held on games held back.
- On the 15 tuning games 5 forecasters looked better (0.1791 against 0.1918, a gain of 0.0127). On the 43 held-back games the gain was 0.0029, below the bar. High effort gained 0.0038 on tuning and was never adopted.
- **Decision: keep 3 forecasters, medium effort.** The stricter flag rules were reported only (2 and 4 flagged bets, nothing to learn from).
- On the held-back games the replayed forecast (0.1989) was no better than the plain AI (0.1955) and behind Kalshi (0.1798).
- Cost: $6.82, against my estimate of $4 to $5. The estimate was low because the test set grew to 43 games and 5 forecasters need 5 calls per game.

## Why Kalshi is hard to beat

- Kalshi's price is made by many people who already know the public facts we find. Anything our research can find is mostly in the price.
- The three forecasters are copies of one model reading the same evidence, so their median adds little.
- The evidence is thin. Many pages block automatic reading (about 204 claims lost) and our own rules for quotes and numbers drop another 114. 18 PDFs and about 13 table cases are not read.
- Fees and the gap between bid and ask take cents from every bet.

## The flag limits

| Limit | Placeholder | What the results say | Decision in this report |
|---|---|---|---|
| `EDGE_MIN` (gap after fees) | 0.05 | 0.08 left 2 bets on the tuning games: too few to judge | keep 0.05 |
| `MIN_SUPPORTED_CLAIMS` | 5 | 8 left 4 bets; scores with 5 or more claims are not clearly better than with fewer | keep 5 |
| `EDGE_PLAUSIBLE_MAX` | 0.15 | no flagged bet is large enough to test it | keep 0.15 |

I am not changing any of the three. No tested value is supported by the results, and picking one that looks good on the same 62 games would be fitting the past. The flag stays a "worth a look" prompt for a person, not a bet instruction. The limits stay placeholders until more games exist.

## Limits of this report

- 62 games is a modest sample. The 485 outcomes are not 485 independent results: the markets of one game (winner, total, spread) move together, so the real sample is about 62.
- Sports with fewer than 20 scored games are "not yet measured" in the app; only soccer (28) and tennis (29) are above that line, and baseball (5) is not.
- Scores say how good the probabilities are. They are not a profit test; the profit numbers use ask prices, no fees, and one contract.
- Matches that had not finished at the time are left out (8 games).

## Options for the next step (not decided)

- Use Kalshi's price as the starting point and let the research only move it a little (a smaller, safer role).
- Add the bookmaker consensus as a second reference (the feed is built and switched off).
- Focus on tennis, the one sport where research helped over the plain AI. 29 games, so first confirm with more.
- Look for structural patterns in historical Kalshi prices (price only, no research). Not checked: whether pre-game price history is available.
- Use the tool as a research assistant for a person, not as a forecaster.

**Recommendation:** real orders (Milestone 7) stay a no-go for now. More finished games are needed, and so far nothing is better than the Kalshi price itself.
