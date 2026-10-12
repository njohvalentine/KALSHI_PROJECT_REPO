# Architecture (Draft for Client Review)

**Status: draft, not final.** This describes the system as it stands after Milestones 1 and 2, and the plan for the rest. Items marked **Open** still need a decision or an answer from you. A step-by-step explanation of the agent graphs is in `docs/agent/GRAPHS.md`.

Last updated: 2026-10-12.

---

## 1. What we are building

An AI research assistant for Kalshi prediction markets, focused on **soccer, baseball and tennis**. You pick a market (for example, "Will Arsenal beat Chelsea on Saturday?"). It researches the question on the web, and in the finished system it will estimate the probability and compare it with Kalshi's price. Every claim comes with a source link. A person decides whether to bet.

**It does not place bets on its own.** Any bet needs a person to approve it. During testing no bets are placed at all.

## 2. What exists today, and what does not

| Part | State |
|---|---|
| Sign-in (one account, created by the operator with a script) | **Built** |
| List of open Kalshi markets with prices | **Built** (tested with simulated Kalshi data; not yet run against the live Kalshi API from our build environment) |
| Research run: a planner chooses angles, several researchers search the web in parallel, results with source links, cost per run | **Built** (tested with simulated OpenAI responses; not yet run with your real OpenAI key) |
| Checking that each source really supports its claim | Planned (Milestone 3) |
| A probability estimate and comparison with Kalshi's price | Planned (Milestone 3) |
| Results dashboard, accuracy testing | Planned (Milestone 4) |
| Approving bets and placing orders | Planned, last, only on your approval |

**Important wording on the result page:** a line marked "Cited" means the search tool attached a source link to it. It does **not** mean the source was checked. Checking comes in Milestone 3.

## 3. How it works

```
 Kalshi market
      |
      v
 [1] LEAD AGENT ........ reads the market, plans which angles to research            (built)
      |
      v
 [2] RESEARCHERS (several, at the same time)
      each searches the web on one angle and returns facts with links                 (built)
      |
      v
 [3] FETCH AND CHECK SOURCES .. reads each cited page, labels claims                  (planned)
      |                         supported / not supported / could not check
      v
 [4] FORECASTERS (three, independent) each estimates the probability                  (planned)
      |
      v
 [5] AGGREGATOR ........ combines the estimates into one probability                  (planned)
      |
      v
 [6] MARKET COMPARER ... compares with Kalshi's price, flags a meaningful gap         (planned)
      |
      v
 [7] HUMAN APPROVAL .... a person approves or rejects a bet                           (planned)
      |
      v
 [8] ORDER STEP ........ sends the bet to Kalshi, only after approval                 (planned)
```

| Step | What it does | Why it exists |
|---|---|---|
| Lead agent | Chooses research angles for this market (injuries and lineups, recent form, head-to-head, venue or surface, probable pitchers, weather, betting odds) | One place decides what is worth looking into |
| Researchers | Each takes one angle, searches the web, returns findings with links | Different angles give different evidence; running them together saves time |
| Fetch and check sources | Opens each cited page and checks the claim against it | So "cited" can become "checked", and the page text is saved for fair testing later |
| Forecasters | Three independent estimates, not shown Kalshi's price | Independent views are steadier than one; not seeing the price stops them just copying it |
| Aggregator | Combines them (median) and records how far apart they were | One clear answer, plus a measure of disagreement |
| Market comparer | Compares with the price a bet could actually be placed at, and shows the estimated gap after fees | A bet only makes sense if we disagree with the market by enough |
| Human approval | A person says yes or no on the exact order | You stay in control of your money |
| Order step | Places the approved bet | Kept separate so an approval can never cause a bet to be sent twice |

### Why this design and not the alternative

We considered two ways to organize the AI agents.

**Design 1 (chosen): one lead agent, with helper agents for each task.** The lead agent plans and hands tasks to helpers (researchers, forecasters). Helpers report back and do not create further helpers.

**Design 2 (rejected): a team of equal agents, each able to create more agents of its own.**

| | Design 1: one lead + helpers (chosen) | Design 2: many agents, each creating more |
|---|---|---|
| Who decides what happens | One place: the lead agent | Spread across several agents |
| Cost | Predictable: hard limit on helpers per run | Can grow unexpectedly |
| Testing | Easy: same steps every run | Hard: the shape of a run changes |
| Debugging | Follow one tree from the lead down | Harder to trace who started what |
| Human approval | One clear stop before any bet | Harder to guarantee |
| Evidence it forecasts better | A published research system uses this shape and reports large gains over a single agent* | None found for this task |

\*Reported as about 90% better on research tasks at about 15 times the AI cost, from secondary summaries; measured on general research, not betting forecasts. We will test it on our own system (section 5).

**What we give up:** helpers cannot restructure the work themselves. **When we would revisit:** only if testing shows the lead agent's limits are holding helpers back, with evidence.

## 4. Technology

| Part | Choice | Reason |
|---|---|---|
| AI models | OpenAI (your key). Planner `gpt-5.4-mini`, researchers `gpt-5.4`, both changeable in settings | You supplied the key |
| Agent framework | LangGraph (Python) | The steps are an explicit, testable flow; it supports parallel helpers, saved progress and pausing for approval |
| Evidence gathering | OpenAI web search tool | Uses your key; returns a link for each source |
| Market data | Kalshi public API (no key needed to read) | Prices, rules and history |
| Backend | FastAPI (Python) | Runs research in the background and serves the web app |
| Web app | Next.js with shadcn/ui, light theme | Pages: Markets, Prediction (research runs and results), Approval, Results |
| Database | PostgreSQL | Runs, results, saved sources, forecasts, accounts, and the agents' saved progress |
| Packaging | Docker Compose: database, backend and web app start together | One command to run everything |
| Tracing | LangSmith (free tier; consent given) | Shows what every agent did and what it cost |
| Sign-in | Email and password, one account created by the operator with a script; no registration page | Single-user tool; a public registration page would let strangers approve bets |

**Open:** whether your OpenAI key works for web search and the chosen models (confirmed only by a first real run).

## 5. How we will know if it works

The honest question is whether the system predicts better than the market price alone. Kalshi prices are already well calibrated, and sports prices especially, so the room to beat them is small. We test before any real money is used.

**Stage 1, backtest on past markets.** Fast and repeatable, good for finding bugs. Caveat: the AI or its search may already know how a past game ended. Results only count once we have a saved copy of the sources to replay (Milestone 3 starts saving page text).

**Stage 2, live paper trading.** The system forecasts open markets and records its predictions. **No bets are placed and no money is at risk.** We score the predictions when the games finish. This is the main test, and sports results arrive within days.

**What we compare, on the same questions:** the full system, one plain AI call with no research, and Kalshi's price. Scores use the Brier score (a standard accuracy measure for probabilities; lower is better).
- If the full system does not beat the plain AI call, the research adds cost without accuracy, and we simplify.
- If it beats the plain call but not Kalshi's price, it is a useful research assistant but not a betting edge.
- If it beats both, it is worth taking further.

The rule for when real betting could be considered is **deferred**; we will agree it after seeing real results.

## 6. Costs

- A research run uses several AI calls plus web searches. Published reports put multi-agent systems at roughly 15 times a normal chat (secondary sources). Prices per million tokens are on OpenAI's pricing page (for example `gpt-5.4`: 2.50 in, 15.00 out); web search costs about 1 cent per search. **Real cost per run is not yet measured**; the result page shows tokens and cost for each run, so the first runs will tell us.
- Built-in limits: at most 4 researchers per run, at most 3 searches each, a cap on output length per call, at most 2 runs at the same time, and one active run per market. A run that costs more than a set warning level is flagged.
- Every press of Analyze spends credit.

## 7. Risks you should know about

1. **No guaranteed edge.** The system may be a good research assistant but not a way to beat the market. The testing in section 5 finds this out cheaply.
2. **Sports contracts are legally contested.** Several US states and federal appeals courts have ruled against Kalshi's sports contracts (as of late September 2026). What you can trade depends on your state. **Open:** your state.
3. **Fees.** Kalshi charges trading fees that reduce small edges; the exact schedule must be confirmed.
4. **Research quality.** Web evidence can be wrong or outdated; checking sources (Milestone 3) reduces this but does not remove it.
5. **Keys.** The Kalshi key was shared in a chat. For real trading, create a new one and share it more safely. Keys are kept only in local settings files, never in the code.

## 8. Questions for you

1. Which US state are you in?
2. Do you trade only match winners, or also other contract types (totals, player props)?
3. Is the Kalshi key a demo key or a production key? (We provide a command that tells you.)
4. Do you want the system to re-check markets from time to time for new information (for example when lineups are announced)? This is proposed, not built.
5. What should "help" cover: finding and researching bets, or also suggesting how much to bet?

## 9. What happens next

1. A first real research run with your OpenAI key, to measure cost, time and quality.
2. Milestone 3: checking sources, forecasts, comparison with the market price (task list needs your approval first).
3. Milestone 4: accuracy testing against the market price.
4. Only then: approval screen and any real orders.
