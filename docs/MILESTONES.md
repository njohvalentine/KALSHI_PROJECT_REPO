# Milestones (Draft for Client Review)

**Status: draft, not final.** This splits the plan in `docs/ARCHITECTURE.md` into stages. Each stage ends with something you can see and approve before we move on.

**No dates or prices yet.** We have not scoped effort, so any timeline would be a guess.

**Ordering principle:** we answer the riskiest question first, which is whether the system predicts better than Kalshi's own price. Real bets come last, and only if the results justify them.

Last updated: 2026-10-15.

---

## Overview

| # | Milestone | You get | Money at risk | State |
|---|---|---|---|---|
| 0 | Confirm and specify | Written specifications to approve | None | Done through Milestone 3 and the extras |
| 1 | Foundation | Sign-in, Kalshi game list, database, tracing, Docker setup | None | **Built** |
| 2 | Research stage | Research runs: planner, parallel researchers, cited findings, cost per run | None | **Built** |
| 3 | Full prediction | Page checking, three forecasts, one probability per outcome, comparison with Kalshi's price | None | **Built** (tested on real games; forecast quality not yet known) |
| 3+ | Extras you asked for | More markets (total goals, runs or points, both teams to score, margin), Opportunities page, Telegram alerts, tickets of several games, all Kalshi sports with the NBA, a replay tool, browser tests; since 2026-10-16 also your six priorities: a daily limit of 5 researched games, a guard against paying twice for a game, an explicit NO BET answer, the bookmaker comparison, a free check against the bookmakers before research, accuracy and simulated result by sport and kind of market, and a risk framework for 100 dollars in paper mode (`docs/RISK-FRAMEWORK.md`) | None | **Built** |
| 4 | Evaluation | Scores against the market price and a plain AI call | None | **Report written** (`docs/ACCURACY-REPORT-2026-10-15.md`); 71 finished games on 2026-10-19: ours 0.194, plain AI 0.195, Kalshi 0.176; no sign of an edge. Price-only tests on 4,709 Kalshi games found no pattern in the price (`docs/discussion/PRICE-TEST-2026-10-19.md`) |
| 5 | Approval screen | Where a person approves or rejects each bet (orders simulated) | None | **Built** (limits are placeholders until you agree yours) |
| 6 | Live paper trading | Weeks of real predictions, scored as games finish | None | **Running** (daily batches of about 30 games; every forecast is recorded and scored) |
| 7 | Go / no-go, then real bets | Decision based on results; optional limited launch | Only if you approve | Not started; the results so far point to no-go for real bets for now |

The web pages: Dashboard, Games, Opportunities, Prediction (runs and results), Approval and Results. The look of the app was redesigned on 2026-10-15 and 2026-10-16 (a Dashboard, tables, a run page with folded sections, a header chip instead of the orange bar), following `docs/design/mockup-redesign-2026-10-15.html`; screenshots are in `docs/design/screenshots-2026-10-16/`.

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

- **Telegram alerts (live since 2026-10-14):** the watcher sends a message when a game becomes worth a look, when a price moves 8 cents or more, or when a flagged game starts within an hour (at most 6 an hour); `scripts/telegram_hello.py` sends a test message.
- **Tickets of several games (combos):** up to 20 bets, several markets of one game allowed, yes or no per bet, any game from the ranking or any market from a run page; the combined numbers are the legs multiplied and are marked rough when bets of one game are on the same ticket. Simulated only.
- **All sports on Kalshi (2026-10-15):** the Games page offers every other sport and league Kalshi lists, loaded when picked; they are marked "not yet measured" until a sport has 20 scored games; the NBA has total points and spread markets.
- **Replay tool (2026-10-14):** re-runs the forecasting step and the flag rule on evidence saved before each finished game, to test ideas without waiting and without a result leaking in (`replay-forecasts`).
- **Browser tests (2026-10-14):** 10 tests for sign-in, the ticket builder, the Approval flow and the Games page.

## Milestone 4: Evaluation
- Brier score; three-way comparison on the same outcomes: our forecast, a plain single AI call with no research, and Kalshi's price; shown per kind of market, with what buying the chosen side at the market price would have paid.
- **Already built:** every live forecast is recorded before the game starts, the result is filled in afterwards, and the command `score-records` prints the scores. **What is missing is data:** about 30 or more finished games before the numbers mean anything.
- Live forecasts are the test to trust (sports results are widely published, so a backtest on past games could be contaminated by what the AI already knows).
- Experiments: showing the forecasters the price as a starting point; splitting evidence between forecasters; other ways of combining estimates; replacing the placeholder limits behind "worth a look" with values chosen from the scores.
- Checks on citation quality and on safety (no order without approval).
- **Status on 2026-10-19 (71 finished games, 553 outcomes with all three; written report `docs/ACCURACY-REPORT-2026-10-15.md`, signal research `docs/discussion/SIGNAL-RESEARCH-2026-10-19.md`):** Brier score (lower is better) ours 0.194, plain AI 0.195, Kalshi 0.176. Our forecasts add nothing to Kalshi's price. 43 flagged bets averaged -11.4 cents per contract after fees (too few to read). The bookmakers match Kalshi within fees; none of 53 screened games was worth researching; the free price tests on Kalshi's own history (4,709 games, an hour to two weeks before the start) found no exploitable pattern. **Still no sign of an edge; the honest conclusion is a research assistant with guardrails, not a proven way to beat the market.**
- **Done when:** a short report is delivered and you decide whether to continue. This may show the system is a good research assistant but cannot beat the market; that is a valid result.

## Bookmaker benchmark (built, switched on with a key)
- Bookmaker odds are saved next to each forecast so the accuracy test can compare our probability with Kalshi's price and with the bookmakers, on the same games. Winner markets only; Challenger tennis is not covered by the odds feed.

## Milestone 5: Approval screen (built, simulated)
- A person prepares an order from an opportunity: the market, whether to buy "yes" or "no", the price at that moment, the number of contracts and the most it can cost. It expires after 10 minutes.
- The Approval page shows the exact order in words and the checks before approving: not expired, game not started, forecast recent, within the betting limits, price has not moved against us, enough contracts offered, still worth a look. A failed check blocks approving.
- A ticket may hold several bets (a combo, up to 20, from several games and several markets of one game): it pays only if every game wins. Its price in the simulation is the games' prices multiplied; a real combo price on Kalshi is quoted on request and will differ. Each leg gets its own checks. Bets on the same game move together, so the combined numbers of such a ticket are marked rough.
- A person presses Approve or Reject. An approved order is placed in a **simulation** by a separate press, which rechecks the price and the limits and records what a bet at that moment would have been; pressing twice, or two people at once, cannot place it twice. When the game ends the order is settled and the Results page shows what it would have paid.
- Every change of an order is kept in a history (who, when, why). **No order is ever sent to Kalshi:** there is no trading code at all.
- **Betting limits (to be agreed with you):** the most you want to risk on one bet and in one day. They are settings; the values in use now are placeholders (10 contracts, 5 dollars per order, 20 dollars per day).

## Milestone 6: Live paper trading
- The system runs on live markets and records predictions. **No bets are placed.** This has started: every run records its forecast.
- The Results page shows the simulated orders and what they would have paid; `score-records` prints the scores of the forecasts.
- The watcher can research upcoming games by itself within a daily cap you set (off by default; each run costs real credit).
- Re-forecasting automatically when news, injuries or lineups change is not built; we first want the scores to show whether updating helps.

## Milestone 7: Go / no-go, then real bets (optional)
- Review the results together; the rule for going live is agreed at that point.
- **If no-go:** keep the system as a research tool, or stop.
- **If go:** a limited launch in steps: Kalshi demo first, then small real bets, a person approving every bet.
- Kalshi's Developer Agreement (terms for automated trading) has not been read yet; this must happen before any real order.
- **State on 2026-10-15:** not started. It also needs the shared Kalshi key replaced, the betting limits and the go-live rule agreed, a real order step (including the combo price request, which Kalshi quotes on request), and the handover checklist. Given the results so far, the honest position is no-go for real bets until the scores show an edge.

---

## Risks that could change the plan
- **Edge is small or absent.** Likely for sports markets. We stop or simplify at Milestone 4 or 6.
- **Sports contracts are legally contested** in several states. Your state decides what is possible.
- **Cost.** Research runs use real credit: about 0.32 to 0.63 USD per game in the real runs.
- **Evidence we cannot read.** Many pages (bookmaker sites, pages built by scripts, PDFs) cannot be read by an automatic reader, so only about a quarter to a half of the cited claims could be confirmed in the real runs.
- **Kalshi access.** Reading Kalshi works; the connection has not been tested from your own network, and the Kalshi key has not been used for anything yet.
