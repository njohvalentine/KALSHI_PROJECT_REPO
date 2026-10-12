# Architecture (Draft for Client Review)

**Status: draft, not final.** This describes the plan as discussed so far. Items marked **Open** still need a decision or an answer from you. Nothing here is built yet.

Last updated: 2026-10-09.

---

## 1. What we are building

An AI research assistant for Kalshi prediction markets. You give it a market (for example, "Will X happen by date Y?"). It researches the question, estimates the probability, and returns a **prediction with sources** for every claim. A person then decides whether to place a bet.

**It does not place bets on its own.** Every bet needs a human to approve it.

## 2. How it works

```
 Kalshi market
      |
      v
 [1] LEAD AGENT ........ reads the market, plans which angles to research
      |
      v
 [2] RESEARCHERS (several, at the same time)
      each checks a different angle and returns facts with links
      |
      v
 [3] FORECASTERS (several, independent)
      each reads the evidence and gives its own probability
      |
      v
 [4] AGGREGATOR ........ combines the estimates into one probability
      |
      v
 [5] CITATION CHECKER .. removes any claim not backed by a real source
      |
      v
 [6] MARKET COMPARER ... compares our probability with Kalshi's price
      |
      v
 [7] HUMAN APPROVAL .... a person approves or rejects the bet
      |
      v
 [8] ORDER STEP ........ sends the bet to Kalshi (only after approval)
```

| Step | What it does | Why it exists |
|---|---|---|
| Lead agent | Plans the research and splits the work | One place decides what to look into |
| Researchers | Each takes a different angle | Different evidence gives better forecasts than everyone reading the same pages |
| Forecasters | Each gives an independent probability | Several independent views are more reliable than one |
| Aggregator | Merges the estimates | Produces one clear answer |
| Citation checker | Keeps only sourced claims | Every statement can be checked |
| Market comparer | Compares us with Kalshi's price | A bet only makes sense if we disagree with the market by a meaningful amount |
| Human approval | A person says yes or no | You stay in control of your money |
| Order step | Places the approved bet | Kept separate so an approval can never cause a bet to be sent twice |

### Why this design and not the alternative

We considered two ways to organize the AI agents.

**Design 1 (chosen): one lead agent, with helper agents for each task.**
One lead agent plans the work and hands tasks to helpers (researchers, forecasters). Helpers do their task and report back. They do not create further helpers.

**Design 2 (rejected): a team of equal agents, where each can create more agents of its own.**
Several agents each own part of the job, and each can start its own sub-agents when it decides it needs them.

| | Design 1: one lead + helpers (chosen) | Design 2: many agents, each creating more |
|---|---|---|
| Who decides what happens | One place: the lead agent | Spread across several agents |
| Cost | Predictable. We set a hard limit on helpers per run | Can grow unexpectedly, because each agent can start more agents |
| Testing | Easy. Same steps every run, so we can test each step | Hard. The shape of a run changes each time |
| Debugging | Follow one tree from the lead down | Harder to trace who started what, and why |
| Human approval | One clear stop before any bet | Harder to guarantee, with several agents able to act |
| Evidence it forecasts better | Published research system from Anthropic uses this shape and reports large gains over a single agent* | None found for this task |
| Flexibility | Fixed pipeline, less free-form | More flexible, but we do not need that here |

\*Anthropic reports about 90% better results than one agent on research tasks, at about 15 times the AI cost. We read this in secondary summaries, since only the introduction of their post was readable. It was measured on general research, not on betting forecasts, so we will test it on our own system (section 4).

**Why the fixed shape suits this project**
- Our job has a clear order: research, then forecast, then combine, then check, then approve. It does not need agents to improvise a structure.
- We are spending real AI budget and, eventually, possibly real money. Predictable cost and one clear approval point matter more here than flexibility.
- Research on AI forecasting suggests gains come from agents seeing *different evidence*, not from having more layers of agents. Design 1 gets that by giving each researcher a different angle.

**What we give up:** if a question needs a research approach we did not plan for, the lead agent can still choose which angles to assign, but the helpers cannot restructure the work themselves. We think that is the right trade for now.

**When we would revisit:** if testing shows the helpers keep hitting limits the lead cannot work around, we can reconsider. We would need evidence first, not just a feeling that more agents is better.

## 3. Technology

| Part | Choice | Reason |
|---|---|---|
| AI models | OpenAI (your API key) | You supplied the key |
| Agent framework | LangGraph (Python) | The steps above become an explicit, testable flow. It saves progress and supports pausing for human approval |
| Evidence gathering | OpenAI web search tool | Uses your existing key and returns a link for each source |
| Market data | Kalshi API | Prices, rules and history for each market |
| Run tracing | LangSmith (free tier) | Shows what every agent did, and what it cost |
| Backend service | FastAPI (Python) | Runs the agents in the background and streams progress to the web app. Uses only free, open-source libraries |
| Web app | Next.js + shadcn/ui | Four pages: market list, prediction detail, bet approval, results |
| Database | PostgreSQL | One database for the agents' saved progress and our own records: each forecast, Kalshi's price at the time, the real outcome, and the pages we cited |

**Open:** where the PostgreSQL database will run (your machine, a cloud service, or Docker).
**Open:** whether your OpenAI key can use the web search tool. We need this confirmed.
**Open:** whether you agree to run traces being sent to LangSmith's cloud service. They contain our prompts and research. If not, we log everything on our side instead.

## 4. How we will know if it works

The honest question is whether the system predicts better than the market price alone. Kalshi prices are already well calibrated, and the room to beat them is small, so we test before any real money is used.

**Stage 1, backtest on past markets.** Fast and repeatable, good for finding bugs. Caveat: the AI or its web search may already know how a past event ended, which would make results look better than they are. Backtest results only count once we have a saved, time-stamped copy of the sources to replay.

**Stage 2, live paper trading.** The system forecasts markets that are still open and records its predictions. **No bets are placed and no money is at risk.** We score the predictions when the markets resolve. This is the main test.

**What we compare, on the same questions:**

| Version | What it is |
|---|---|
| A. Full system | The pipeline above |
| B. Single AI call | One plain request, no research |
| C. Kalshi's price | The market's own probability |

We score each with the Brier score (a standard accuracy measure for probabilities; lower is better).
- If A does not beat B, the extra research adds cost without accuracy, and we simplify.
- If A beats B but not C, it is a useful research assistant but not a betting edge.
- If A beats both, it is worth taking further.

**Proposed bar for going live (needs your agreement):** only consider real bets if, over an agreed number of resolved questions, the full system scores better than both the market price and the single AI call, by more than normal run-to-run variation. **Open:** the number of questions and any bar of your own.

## 5. Costs and limits

- A multi-agent run uses far more AI tokens than a normal chat. Published reports put it at roughly 15 times (secondary sources, not measured on our system yet). We will cap how many researchers and forecasters a run can use. Proposed starting caps: up to 4 researchers and 3 forecasters. **Open:** your monthly spend limit and which OpenAI models are allowed.
- LangSmith free tier: 5,000 traces per month, kept 14 days. A busy month could exceed this. We will measure on real runs.
- Betting limits (per bet and per day) must be set by you. **Open.**

## 6. Risks you should know about

1. **No guaranteed edge.** The system may turn out to be a good research assistant but not a way to beat the market. The testing in section 4 exists to find that out cheaply.
2. **Sports contracts are legally contested.** Several US states and federal appeals courts are currently ruling against Kalshi's sports contracts (as of late September 2026). Where you live affects which markets you can use. **Open:** your state and which market types you want.
3. **Fees.** Kalshi charges trading fees that reduce small edges. Exact fees must be confirmed from Kalshi's current schedule.
4. **Research quality.** Web evidence can be wrong or outdated. The citation checker reduces this, but does not remove it.

## 7. Questions for you

1. Which market types do you want (sports, economics, politics, weather, other)?
2. Which US state are you in?
3. Whose Kalshi account and money will be used? What are the per-bet and daily limits?
4. Should the system only find and research bets, or also suggest how much to bet?
5. Which OpenAI models are allowed, is there a monthly spend cap, and can your key use web search?
6. Do you agree to traces being sent to LangSmith's cloud?
7. Do you accept the go-live bar in section 4, or do you have your own?

## 8. What happens next

1. You answer the questions above.
2. We write a detailed specification for your approval.
3. We build the system step by step, starting with paper trading only (no real bets).
4. We review the paper-trading results together before any decision on real money.
