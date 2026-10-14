# Milestones (Draft for Client Review)

**Status: draft, not final.** This splits the plan in `docs/ARCHITECTURE.md` into stages. Each stage ends with something you can see and approve before we move on.

**No dates or prices yet.** We have not scoped effort, so any timeline would be a guess.

**Ordering principle:** we answer the riskiest question first, which is whether the system predicts better than Kalshi's own price. Real bets come last, and only if the results justify them.

Last updated: 2026-10-13.

---

## Overview

| # | Milestone | You get | Money at risk | State |
|---|---|---|---|---|
| 0 | Confirm and specify | Written specifications to approve | None | Done through Milestone 3 and the extras |
| 1 | Foundation | Sign-in, Kalshi game list, database, tracing, Docker setup | None | **Built** |
| 2 | Research stage | Research runs: planner, parallel researchers, cited findings, cost per run | None | **Built** |
| 3 | Full prediction | Page checking, three forecasts, one probability per outcome, comparison with Kalshi's price | None | **Built** (tested on real games; forecast quality not yet known) |
| 3+ | Extras you asked for | More markets (total goals or runs, both teams to score, margin), Opportunities page, alerts and optional automatic research | None | **Built**; chat alerts wait for your choice of application |
| 4 | Evaluation | Scores against the market price and a plain AI call | None | Planned; needs about 30 or more finished games |
| 5 | Approval screen | Where a person approves or rejects each bet (orders simulated) | None | **Built** (limits are placeholders until you agree yours) |
| 6 | Live paper trading | Weeks of real predictions, scored as games finish | None | Started (every forecast is recorded) |
| 7 | Go / no-go, then real bets | Decision based on results; optional limited launch | Only if you approve | Planned |

The web pages: Games, Opportunities, Prediction (runs and results), Approval and Results. Approval and Results come later.

---

## Milestone 0: Confirm and specify
- Questions answered, specifications written and approved before each build.
- **Done:** Milestones 1, 2 and 3 and the extras.
- Still open from you: your US state, which leagues and tours, which chat application, whether "help" includes bet sizing, a new Kalshi key.

## Milestone 1: Foundation (built)
- Docker Compose runs the database, backend and web app together.
- One-account sign-in (account created by the operator with a script), session cookie, lockout after repeated failures.
- Read-only connection to Kalshi: games, outcomes, prices, fees. No Kalshi key is needed to read.
- Database tables managed with migrations; LangSmith tracing.
- Web app: shared layout, login page, the Games page.

## Milestone 2: Research stage (built)
- A lead agent plans up to 4 research angles written for soccer, baseball and tennis.
- Researchers run in parallel, each forced to use web search (at most 3 searches), and return one fact per line with source links taken from the search tool's own citations.
- Runs go in the background; one run per game; at most 2 at once; interrupted runs are marked failed.
- Web app: the **Games page** (upcoming games from a configured league list, soonest first, start time in your time zone, buy and sell prices, sport filter and search), a Research button per game, a run list and a result page that updates itself.

## Milestone 3: Full prediction (built)
- Each cited page is downloaded safely (public addresses only, size and time limits) and its text is saved with the time it was read.
- Every claim is checked against its page: supported, the page says something different, or could not check. A verdict needs an exact quote from the page. Only supported claims go forward; the rest stay visible. Wrong claims were caught in real runs.
- Three independent forecasters (they never see Kalshi's price) estimate every outcome; the middle estimate is the forecast, and the lowest and highest are kept. A plain AI call with no research is recorded for comparison.
- The forecast is compared with the price a bet could really be placed at, after Kalshi's fee. A gap is marked "worth a look" only if it is large enough but not suspiciously large, the research moved the estimate away from the plain AI call toward the gap, the forecasters agree, enough claims were supported and enough contracts are on offer. It is a flag, never a recommendation; the limits are placeholders until the evaluation.
- Web pages: the result page (forecast and market, the forecasts, the evidence with each claim's check result, the pages that could not be read, the cost per step) and the Games list with our estimates.
- **Measured on real games:** about 1 to 1.5 minutes and 0.32 to 0.63 USD per game.

## Extras you asked for (built)
- **More markets:** total goals or runs, both teams to score and margin of victory are forecast in the same run as the winner, with checks that related markets agree (for example, a higher goal line is never more likely than a lower one). Tie and no tie are the two sides of the Tie market. Further types Kalshi offers (first half, corners, team totals, tennis scores) can be added the same way.
- **Opportunities page:** researched games that have not started, ranked by the gap after fees at today's prices, one row per game, with the risks in plain words.
- **Watcher and alerts:** alerts when a game is worth a look, when the market moves a lot since the forecast, when it stops being worth a look, and when a flagged game starts soon. For now they appear in the app; they go to a chat message once you tell us the application. Optional automatic research of upcoming games is off and capped.

## Milestone 4: Evaluation
- Brier score; three-way comparison on the same outcomes: our forecast, a plain single AI call with no research, and Kalshi's price; shown per kind of market, with what buying the chosen side at the market price would have paid.
- **Already built:** every live forecast is recorded before the game starts, the result is filled in afterwards, and the command `score-records` prints the scores. **What is missing is data:** about 30 or more finished games before the numbers mean anything.
- Live forecasts are the test to trust (sports results are widely published, so a backtest on past games could be contaminated by what the AI already knows).
- Experiments: showing the forecasters the price as a starting point; splitting evidence between forecasters; other ways of combining estimates; replacing the placeholder limits behind "worth a look" with values chosen from the scores.
- Checks on citation quality and on safety (no order without approval).
- **Done when:** a short report is delivered and you decide whether to continue. This may show the system is a good research assistant but cannot beat the market; that is a valid result.

## Milestone 5: Approval screen (built, simulated)
- A person prepares an order from an opportunity: the market, whether to buy "yes" or "no", the price at that moment, the number of contracts and the most it can cost. It expires after 10 minutes.
- The Approval page shows the exact order in words and the checks before approving: not expired, game not started, forecast recent, within the betting limits, price has not moved against us, enough contracts offered, still worth a look. A failed check blocks approving.
- A ticket may hold several bets (a combo, up to 20, from several games and several markets of one game): it pays only if every game wins. Its price in the simulation is the games' prices multiplied; a real combo price on Kalshi is quoted on request and will differ. Each leg gets its own checks. Bets on the same game move together, so the combined numbers of such a ticket are marked rough.
- A person presses Approve or Reject. An approved order is placed in a **simulation** by a separate press, which rechecks the price and the limits and records what a bet at that moment would have been; pressing twice, or two people at once, cannot place it twice. When the game ends the order is settled and the Results page shows what it would have paid.
- Every change of an order is kept in a history (who, when, why). **No order is ever sent to Kalshi:** there is no trading code at all.
- **Betting limits (to be agreed with you):** the most you want to risk on one bet and in one day. They are settings; the values in use now are placeholders (10 contracts, 5 dollars per order, 20 dollars per day).

## Milestone 6: Live paper trading
- The system runs on live markets and records predictions. **No bets are placed.** This has started: every run records its forecast.
- The Results page (to be built) shows forecast, Kalshi price and outcome as games finish.
- The watcher can research upcoming games by itself within a daily cap you set (off by default; each run costs real credit).
- Re-forecasting automatically when news, injuries or lineups change is not built; we first want the scores to show whether updating helps.

## Milestone 7: Go / no-go, then real bets (optional)
- Review the results together; the rule for going live is agreed at that point.
- **If no-go:** keep the system as a research tool, or stop.
- **If go:** a limited launch in steps: Kalshi demo first, then small real bets, a person approving every bet.
- Kalshi's Developer Agreement (terms for automated trading) has not been read yet; this must happen before any real order.

---

## Risks that could change the plan
- **Edge is small or absent.** Likely for sports markets. We stop or simplify at Milestone 4 or 6.
- **Sports contracts are legally contested** in several states. Your state decides what is possible.
- **Cost.** Research runs use real credit: about 0.32 to 0.63 USD per game in the real runs.
- **Evidence we cannot read.** Many pages (bookmaker sites, pages built by scripts, PDFs) cannot be read by an automatic reader, so only about a quarter to a half of the cited claims could be confirmed in the real runs.
- **Kalshi access.** Reading Kalshi works; the connection has not been tested from your own network, and the Kalshi key has not been used for anything yet.
