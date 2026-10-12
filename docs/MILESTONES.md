# Milestones (Draft for Client Review)

**Status: draft, not final.** This splits the plan in `docs/ARCHITECTURE.md` into stages. Each stage ends with something you can see and approve before we move on.

**No dates or prices yet.** We have not scoped effort, so any timeline would be a guess.

**Ordering principle:** we answer the riskiest question first, which is whether the system predicts better than Kalshi's own price. Real bets come last, and only if the results justify them.

Last updated: 2026-10-12.

---

## Overview

| # | Milestone | You get | Money at risk | State |
|---|---|---|---|---|
| 0 | Confirm and specify | Written specifications to approve | None | Done for Milestones 1 and 2; Milestone 3 plan awaiting approval |
| 1 | Foundation | Sign-in, Kalshi market list, database, tracing, Docker setup | None | **Built** (live Kalshi check still to be run) |
| 2 | Research stage | Research runs: planner, parallel researchers, cited findings, cost per run | None | **Built** (first real run with your OpenAI key still to be done) |
| 3 | Full prediction | Source checking, three forecasts, one probability, comparison with Kalshi's price | None | Planned; task list waiting for approval |
| 4 | Evaluation | Scores against the market price and a plain AI call | None | Planned |
| 5 | Approval screen | Where a person approves or rejects each bet (orders simulated) | None | Planned |
| 6 | Live paper trading | Weeks of real predictions, scored as games finish | None | Planned |
| 7 | Go / no-go, then real bets | Decision based on results; optional limited launch | Only if you approve | Planned |

The web pages (Markets, Prediction, Approval, Results) are built across milestones: Markets and Prediction exist now; Approval and Results come later. A sign-in page exists now.

---

## Milestone 0: Confirm and specify
- Questions answered, specifications written and approved before each build.
- **Done:** Milestones 1 and 2. **Waiting:** Milestone 3 task list (see `docs/discussion/NOTEPAD.md`, D23).
- Still open from you: your US state, which contract types you trade, whether to add periodic re-checks.

## Milestone 1: Foundation (built)
- Docker Compose runs the database, backend and web app together.
- One-account sign-in (account created by the operator with a script), session cookie, lockout after repeated failures.
- Read-only connection to Kalshi: markets, events, price history. No Kalshi key is needed for this.
- Database tables managed with migrations; LangSmith tracing; LangGraph's saved progress in Postgres.
- Web app: shared layout, login page, and the Games page (later rebuilt as one row per game, see Milestone 2).
- A command that tells whether the Kalshi key is demo or production (`check-kalshi-key`).
- Found and fixed along the way: a login lockout race, sessions surviving a password change, a login flood risk, and slow failures when Kalshi is unreachable.
- **Done when:** a real market list loads and a traced test run is visible. **Still to do:** run the Kalshi check and the live market list from a machine that can reach Kalshi.

## Milestone 2: Research stage (built)
- A lead agent plans up to 4 research angles written for soccer, baseball and tennis.
- Researchers run in parallel, each forced to use web search (at most 3 searches), and return findings with source links taken from the search tool's own citations.
- Every cited page is recorded with its link, title, time and the claims it was cited for. This is a record of what each source was used for, not a copy of the page (OpenAI's citations carry no page text); real page text is saved in Milestone 3.
- Runs go in the background; **one run per game**; one active run per game, at most 2 at once; interrupted runs are marked failed.
- Web app: the **Games page** (upcoming soccer, baseball and tennis games from a configured league list, soonest first, with start time in your time zone, buy and sell prices for each outcome, sport filter and search, already-started games hidden by default), a Research button per game, a list of runs, and a result page that updates itself while the run works and shows findings, source links, tokens and cost.
- **Done when:** for a sample of real markets, each result lists findings with working links and shows its cost. **Still to do:** the first run with your real OpenAI key.

## Milestone 3: Full prediction (planned, not approved)
- Fetch each cited page safely and save its text (this is also the page record that fair backtests need).
- Check each claim against its page: supported, not supported, or could not check. Only supported claims go forward; the rest stay visible.
- Three independent forecasters estimate the probability (they are not shown Kalshi's price); the estimates are combined with the median and their spread is recorded.
- Compare with the price a bet could actually be placed at; show the gap and the estimated edge after fees; flag a gap as meaningful only if it is large enough, the forecasters agree and the evidence is not thin.
- Web app: probability for each outcome of the game, the gap bar, each forecaster's estimate, each claim's check result; the Games list gets an estimate and gap column.
- **Done when:** for any market, the system returns one probability, its reasoning, checked citations and the comparison, with the cost of the run.

## Milestone 4: Evaluation
- Brier score; three-way comparison on the same questions: full system, a plain single AI call, and Kalshi's price.
- Backtest on past markets, labelled not fully reliable until the saved page record is large enough; sports results are widely published, so live testing is the one to trust.
- Experiments: showing the forecasters the price as a starting point; splitting evidence between forecasters; other ways of combining estimates.
- Checks on citation quality and on safety (no order without approval).
- **Done when:** a short report is delivered and you decide whether to continue. This may show the system is a good research assistant but cannot beat the market; that is a valid result.

## Milestone 5: Approval screen
- The approval page: the exact order (market, side, price, quantity), checks before sending, an expiry time, approve or reject. Orders are still simulated.
- A prepared order is a separate step after approval, rechecks the price, and cannot be sent twice.
- Betting limits are agreed here, before any real order exists.

## Milestone 6: Live paper trading
- The system runs on live markets and records predictions. **No bets are placed.**
- The Results page shows forecast, Kalshi price and outcome as games finish.
- Optionally, periodic re-checks for new information such as announced lineups (proposed, not built; each re-check is another run and spends credit).

## Milestone 7: Go / no-go, then real bets (optional)
- Review the results together; the rule for going live is agreed at that point.
- **If no-go:** keep the system as a research tool, or stop.
- **If go:** a limited launch in steps: Kalshi demo first, then small real bets, a person approving every bet.
- Kalshi's Developer Agreement (terms for automated trading) has not been read yet; this must happen before any real order.

---

## Risks that could change the plan
- **Edge is small or absent.** Likely for sports markets. We stop or simplify at Milestone 4 or 6.
- **Sports contracts are legally contested** in several states. Your state decides what is possible.
- **Cost.** Research runs use real credit. The first live runs will give real numbers.
- **Kalshi access.** The live Kalshi connection and the key have not yet been tested from our build environment.
