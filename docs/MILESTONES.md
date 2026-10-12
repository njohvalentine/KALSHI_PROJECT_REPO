# Milestones (Draft Proposal for Client Review)

**Status: draft, not final.** This splits the plan in `docs/ARCHITECTURE.md` into stages. Each stage ends with something you can see and approve before we move on.

**No dates or prices yet.** We have not scoped effort, so any timeline would be a guess. We will add estimates once the specification (Milestone 0) is approved.

**Ordering principle:** we answer the riskiest question first, which is whether the system predicts better than Kalshi's own price. Real bets come last, and only if the results justify them.

---

## Overview

| # | Milestone | You get | Money at risk |
|---|---|---|---|
| 0 | Confirm and specify | Written specification to approve | None |
| 1 | Foundation | Live Kalshi market data and run tracing | None |
| 2 | Research stage | Researchers that return cited evidence | None |
| 3 | Full prediction pipeline | A prediction with sources for any market | None |
| 4 | Evaluation | Scores against the market price and a single-AI baseline | None |
| 5 | Web app | Four polished pages, including bet approval | None (orders are simulated) |
| 6 | Live paper trading | Weeks of real predictions, scored as markets resolve | None |
| 7 | Go / no-go, then real bets | Decision based on results. Optional limited launch | Only if you approve |

---

## Milestone 0: Confirm and specify

**Goal:** remove open questions before building anything.

**Work**
- Get your answers to the open questions in `ARCHITECTURE.md`, section 7.
- Confirm that your OpenAI key can use the web search tool.
- Write a detailed specification: data tables, agent inputs and outputs, limits, testing plan.

**You approve:** the specification, the go-live bar (section 4 of `ARCHITECTURE.md`), and spending limits.

**Done when:** the specification is signed off.

---

## Milestone 1: Foundation

**Goal:** the project runs end to end on real data, with nothing intelligent yet.

**Work**
- Project setup (Python backend, Next.js frontend, project-local installs only).
- Read-only connection to Kalshi: list markets, read one market, price history. Tested on Kalshi's demo environment first.
- Our own database table for forecasts, Kalshi prices, outcomes, and saved source pages.
- LangSmith tracing switched on.
- Startup checks: the system refuses to start if a required key or setting is missing.

**Done when:** we can pull a real market and see a traced test run.

---

## Milestone 2: Research stage

**Goal:** given a market, produce well-sourced evidence.

**Work**
- Lead agent that plans which angles to research.
- Researchers that run in parallel, each on a different angle, using OpenAI web search.
- Every cited page saved with a timestamp (this builds the saved record that fair backtests need).
- Hard cap on researchers per run.

**Done when:** for a sample of markets, each research report lists claims with working links, and we can show the cost per run.

---

## Milestone 3: Full prediction pipeline

**Goal:** a complete prediction with sources, still with no betting.

**Work**
- Forecasters that each give an independent probability.
- Aggregator that combines them.
- Citation checker that removes unsupported claims.
- Market comparer that flags large gaps against Kalshi's price.
- Hard cap on forecasters per run. Order step exists but is switched off.

**Done when:** for any chosen market, the system returns one probability, its reasoning, and checked citations, and we can show what each agent did in LangSmith.

---

## Milestone 4: Evaluation

**Goal:** find out whether the system is any good, before building more on it.

**Work**
- Scoring with the Brier score (a standard accuracy measure; lower is better).
- Three-way comparison on the same questions: full system, a single plain AI call, and Kalshi's price.
- Backtest on past markets. Results are labeled as not fully reliable until our saved source record is large enough to avoid hindsight leaks (see `ARCHITECTURE.md`, section 4).
- Checks on citation quality and on safety (no order without approval).

**You approve:** a short report. If the full system does not beat the single AI call, we discuss simplifying before spending more.

**Done when:** the report is delivered and you decide whether to continue.

**Honest note:** this milestone may show that the system is a good research assistant but cannot beat the market. That is a valid result, and it is much cheaper to learn here than later.

---

## Milestone 5: Web app

**Goal:** a polished interface for your team.

**Work**
- Next.js app with shadcn/ui, light theme, one shared page width and layout on every page.
- Four pages: market list, prediction detail (probability, reasoning, sources), bet approval, results dashboard (forecast vs Kalshi price vs outcome).
- Approval flow: a person approves or rejects. In this milestone approved orders are simulated, not sent.
- Visual mockups reviewed with you before we build the pages.

**Done when:** you can walk through a market from list to approval on a desktop and a phone screen.

---

## Milestone 6: Live paper trading

**Goal:** the real test. Predict open markets, score them when they resolve.

**Work**
- System runs on live markets and records predictions. **No bets are placed.**
- Results dashboard updates as markets resolve.
- Spend and trace volume monitored against your limits.

**Length:** depends on how fast markets resolve and how many questions the go-live bar needs. We will set this in the specification.

**Done when:** the agreed number of resolved questions is reached.

---

## Milestone 7: Go / no-go, then real bets (optional)

**Goal:** a decision based on evidence.

**Work**
- Review the results against the agreed bar together.
- **If no-go:** we keep the system as a research tool, or stop.
- **If go:** limited launch, in steps: Kalshi demo environment first, then small real bets with your per-bet and daily limits, a person approving every bet.

**Done when:** you decide. Real-money steps start only on your written approval.

---

## Risks that could change the plan

- **Edge is small or absent.** Likely outcome of Milestone 4 or 6. We stop or simplify there.
- **Sports contracts are legally contested** in several states. Your state and market types affect what we can build for.
- **Cost.** Multi-agent runs use far more AI budget than a chat. We measure it in Milestone 2 and set caps.
- **Tracing limits.** LangSmith's free tier may run out. We measure it, and have a fallback of logging on our side.
