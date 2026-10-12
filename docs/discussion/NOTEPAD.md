# Discussion Notepad

Read this first. It explains what we are building, every route we chose and why, what we rejected, and what is still open.
It is a discussion log, not tracking. Approved work items go in `TODO.md` (CLAUDE.md Module 7). No spec or code exists yet.
Last updated: 2026-10-09.

---

## Current status (read this first; end of session on 2026-10-12)

- **Code:** `master` holds Milestones 1 and 2. **Branch `feature/sports-games-list` (last commit `3743cbf`, not merged, no remote) is where the live work is** and is what the running Docker stack was built from. 169 backend tests pass; the web app has no automated tests (lint, build and browser checks only).
- **What works, checked live (VPN on, real OpenAI key, public Kalshi calls only):** sign-in; Games page (15 configured series, about 334 games, one row per game, kickoff time from Kalshi milestones, buy and sell prices, sport filter, search, started games hidden); research per game (planner, parallel researchers, cited claims, cost). Four real runs: $0.26 to $0.33 each, 28 to 48 s, current dated odds, no markdown (D27, D28).
- **Kalshi facts that bit us (D25, D29):** `occurrence_datetime` is settlement time, real kickoff is in `GET /milestones` (needs `limit`); `last_price_dollars` is often 0 where bid and ask exist; combination markets need `mve_filter=exclude`; no category filter on markets or events, only on series.
- **Not verified:** research quality beyond four games; behaviour on the client's own network (the 10 s first load is the user's VPN); anything about placing orders (never to be called without approval); Kalshi's Developer Agreement (unread).
- **The user's setup rules:** never write `.env` (they own secrets); Kalshi reachable from here only with their VPN on; demo account `demo@example.com` exists locally; the Kalshi key is a production key, valid, shared over WhatsApp (client must rotate; handover checklist in D24).
- **Next step the user wants:** a Milestone 3 plan **per game** (one probability per outcome) for approval (D23, D26); then merge decision for the branch.

---

## 1. The goal (what and why)

**What:** a multi-agent AI system for the client that researches a Kalshi market, plans, and returns a **probability prediction with citations**. A human approves any bet.

**Why this shape:** the client wants help deciding bets, not a bot that spends their money. Research -> planning -> result with citations makes every prediction checkable.

**Honest caveat (we keep this in view):** an AI only makes money if it beats the market price. Kalshi prices are already well calibrated, and the reported room for an edge is tiny (about 0.01-0.03 Brier, a score where lower is better). Fees also eat small edges. So the system may end up as a research assistant, not a money machine. The evaluation (section 5) exists to find that out before any real money is used.

---

## 2. Background: Kalshi (so nobody has to re-research)

Source quality: many web sources are affiliate/SEO guides. Items marked *unverified* rest on one source.

- **What it is:** US exchange for yes/no event contracts priced $0.01-$0.99. Pays $1 if yes. Kalshi is the marketplace, not the other side of your bet.
- **Regulation:** CFTC-approved Designated Contract Market (2020) and registered clearing organization. Customer funds segregated. US users 18+, brokerage-style ID checks.
- **Fees:** taker fee about `0.07 x price x (1 - price)`, highest near 50 cents. Makers mostly pay zero. Sources disagree, so check Kalshi's current schedule before relying on it. A "fee-free for winners" claim is unverified; ignore it.
- **API:** REST, WebSocket, FIX. Docs: docs.kalshi.com.
  - REST prod `https://external-api.kalshi.com/trade-api/v2`, demo `https://external-api.demo.kalshi.co/trade-api/v2`.
  - WebSocket prod `wss://external-api-ws.kalshi.com/trade-api/ws/v2`, demo uses the `.demo.kalshi.co` host.
  - Auth: API key ID + signature from a private key + timestamp headers. Demo and prod keys are not interchangeable. Some third-party guides are outdated (old v1 URL, "30 minute token"), so use official docs only.
- **Legal risk (as of late Sep 2026):** sports contracts are the weak spot (reportedly ~89% of fees, *unverified*).
  - 9th Circuit (Aug 28) and 6th Circuit (Sep 25) ruled states can regulate them. Kalshi geofenced Ohio and Tennessee.
  - Massachusetts injunction (Jan), New York $36B suit (Jul 31), Connecticut suit (Aug). Reports say "a dozen+" to "~20" states act against it. A nationwide class action is pending. Supreme Court petition reported, status not found.
  - The CFTC (Chair Selig) backs Kalshi.
  - **Why it matters to us:** if the client picks sports markets, their state's law could affect them. This is why market genre is an open question (section 6).
- **Funding:** reported $1B Series F at $22B valuation (May 2026), *unverified*.

---

## 3. Decisions (what / why / rejected / how)

### D1. Users: the client only
- **Why:** offering it to the client's customers would bring licensing and legal exposure far beyond this job.
- **Rejected:** a product for the client's end users.

### D2. A human approves every bet
- **Why:** an AI moving real money needs a human check. It also keeps a person making each bet, which helps with the state-law risk above.
- **Rejected:** suggest-only (too little value); fully automatic with spending caps (too risky before we have evidence of an edge).
- **How:** LangGraph `interrupt()` pauses the run and waits for approve/reject (see D4). The order is placed in its own step *after* approval (see gotcha in D4).

### D3. Architecture: one master agent that spawns subagents, fixed pipeline, one level deep
- **Why:** Anthropic's research system uses this shape (a lead agent plus parallel searchers). They report it beat a single agent by about 90% on research tasks at roughly 15x the tokens (secondary summaries, since only the intro of their post was readable). A fixed pipeline is easy to test and control.
- **Client-facing version:** the full comparison table (cost, testing, debugging, approval, evidence) is in `docs/ARCHITECTURE.md`, section 2, "Why this design and not the alternative".
- **Rejected:** several agents that each spawn their own agents. More cost and less control, and I found no evidence it forecasts better.
- **How (the agents):**

| Stage | Agent | Job |
|---|---|---|
| Research | Lead / planner | Reads the market, writes the plan, splits the work |
| Research | Researchers (parallel) | Each digs a *different* angle or source set, returns facts with links |
| Planning | Forecasters (parallel, independent) | Each gives its own probability and reasoning |
| Result | Aggregator | Combines estimates (median or weighted), calibrates |
| Result | Citation checker | Rejects any claim not backed by a real source |
| Result | Market comparer | Compares final probability to Kalshi's price, flags only large gaps |
| Result | Human approval | See D2 |

- **Why researchers get different angles:** a 2026 preprint (InfoDelphi) finds multi-agent forecasting helps mainly when agents see *different* evidence. Same evidence just reinforces the same view. Preprints, small samples, so treat as a lead.

### D4. Framework: LangGraph
- **Constraint that forced this choice:** the client gave an **OpenAI API key**. The Claude Agent SDK only runs Claude models, so it is out.
- **Compared on official docs and PyPI** (not blogs): LangGraph 1.2.14 and OpenAI Agents SDK 0.23.1. Both need Python >=3.10 (ours is 3.13.11; 3.13 specifically not confirmed on either page).
  - Both can do everything we need: parallel workers, structured output, human approval, saved state. The difference is style.
  - **OpenAI Agents SDK:** less code. Master agent calls specialists with `Agent.as_tool()`; parallel via `asyncio.gather`; built-in tracing; approval via `needs_approval=True`. Tied to OpenAI by default, heavier dependencies.
  - **LangGraph:** more code, but the pipeline is an explicit graph, so each stage is visible and testable. Saves progress (matters: a run costs real tokens). Lighter dependencies, model-agnostic.
- **Why LangGraph:** the user leaned this way, and a fixed pipeline with approval and saved state fits a graph naturally.
- **Rejected:** OpenAI Agents SDK (fine choice, would also work; picked less on merit than on fit and preference). Pydantic AI (single-agent focus, multi-agent claim unverified). Plain Python (we would rebuild orchestration).
- **How "spawning" works** (official docs): there is no spawn call.
  1. The lead node asks the LLM for a structured plan (e.g. a list of research angles).
  2. A routing function returns one `Send("researcher", {"angle": a})` per item. Each is a parallel worker with its own small state.
  3. A shared state field declared `Annotated[list, operator.add]` merges every worker's result. Without this merge rule, workers overwrite each other.
  4. A normal edge to the next node runs only after all workers finish.
  5. Two fan-outs in a row: researchers, then forecasters. A worker can itself be a small graph (subgraph) but we stay one level deep.
  - **Gotcha - double orders:** when a run resumes after approval, the node *re-runs from its start*. If the approval and the order are in the same node, a bet could be sent twice. So: order placement is its own node after the approval node.
  - **Gotcha - cost:** every `Send` is a separate model run, so the lead must be capped (planned default, to confirm in spec: up to 4 researchers, 3 forecasters).
  - **Gotcha - testing needed:** calling the same subgraph in parallel on one thread can clash on saved state (docs). Test before relying on it.
  - Don't wrap `interrupt()` in a bare try/except, it works by raising an exception.

### D5. Observability: LangSmith free tier + our own table
- **Why:** LangSmith traces LangGraph with two environment variables (`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`) and shows each run as a tree. That covers debugging and cost. It does *not* track forecast vs market vs real outcome, which we need for evaluation anyway, so we keep our own table (forecast, Kalshi price at the time, outcome).
- **Limits (official pricing page):** free = 1 seat, 5k base traces a month, kept 14 days. Paid = $39/seat/month for 10k traces. Self-hosting is Enterprise only.
- **Rejected:** Langfuse self-hosted (needs Postgres, Redis, ClickHouse and S3; its Docker Compose option is a single machine with no backups). Fully own logging (we would build the viewing screens ourselves). Kept as the fallback if the client refuses cloud tracing.
- **Open risk:** 5k traces/month may run out fast with multi-agent runs. Measure on real runs.
- **Open risk:** traces contain prompts and the client's reasoning. **Client consent to send them to LangSmith's cloud has not been confirmed.**

### D6. Evaluation: backtest, then live paper trading, no real orders
- **What "paper trading" means:** the agent only *records* predictions. Nothing is ordered, so no money is at risk. The order tool is mocked during all evals (LangSmith supports `config={"env": "test"}` for this).
- **Why two stages:**
  - *Backtest on past markets:* fast and repeatable, good for catching bugs and comparing versions. Risk: **leakage**, because the model or web search may already know the answer.
  - *Live paper trading on open markets, scored when they resolve:* no leakage, so this is the real test, but it takes weeks. This is how ForecastBench works.
- **Leakage guards (from research):** use questions that resolved after the model's training cutoff; limit search to pages dated before the question opened; flag suspicious questions with a judge model and re-score without them (one study found under 1% change, but the detector is imperfect).
- **What we measure:**
  1. Brier score of final probabilities vs outcomes.
  2. Calibration (do 70% calls happen ~70% of the time). Method not found in sources; the usual one is binning forecasts, *unverified*.
  3. Citation quality: code check that each claim has a link, plus an LLM judge that the source supports the claim.
  4. Process: LangSmith trajectory checks (did the lead plan, did the citation checker run) and single-stage tests.
  5. Safety: no order without approval.
- **Three-way comparison, same questions:** (A) full pipeline, (B) one plain OpenAI call with no research, (C) Kalshi's own price.
  - A does not beat B: research and multi-agent parts add cost, no accuracy. Simplify.
  - A beats B but not C: a research assistant, not a betting edge.
  - A beats both: worth taking further.
  - **Why B matters:** the pipeline costs ~15x tokens, and the research found news retrieval did not consistently help LLM forecasts.
- **Why raw Brier can mislead:** it breaks down when forecasters answer different questions (ForecastBench uses a difficulty-adjusted score). We compare on the *same* questions.
- **Go-live bar (my suggestion, NOT from a source, needs client sign-off):** only go live if, over an agreed number of resolved live questions, A scores better than C *and* better than B, with a gap bigger than run-to-run noise. The question count is TBD (to work out in the spec).
- **Reference numbers:** random predictor ~0.333 Brier, general public ~0.121, frontier LLMs ~0.122-0.136, superforecasters ~0.096 (ForecastBench via the Foresight Arena paper; early-2025 figures, leaderboard may have changed).

### D6 correction (found while researching data sources)
- I earlier listed "limit search to pages dated before the question opened" as a leakage guard. **Research says that guard is not enough.** A 2026 paper (arxiv 2602.00758) found date-filtered Google/DuckDuckGo results still had major post-cutoff leakage for 71% / 81% of questions (updated articles, "related content" boxes, wrong metadata). They recommend frozen, time-stamped web snapshots. Also, OpenAI's web search tool has **no date filter at all** (official docs).
- **Consequence:** live web search is only trustworthy for *live paper trading*. A fair *backtest* needs a frozen snapshot of sources (see D7). Until we have one, backtest results using live search must not be trusted.

### D7. Data sources for researchers (DECIDED: start with option A, OpenAI web search)
- **Decision (2026-10-09):** start with Source 2 option A. **Why:** it uses the client's existing key, needs no new vendor or dependency approval, and returns URL citations we need anyway. **How we cover its gaps:** (1) force search with `tool_choice: required` so the model can't skip it; (2) save every cited page with a timestamp into our own table, building a frozen snapshot for later backtests (see D6 correction); (3) if the client's key cannot use web search, or we need controlled page text, add option B (needs Module 5 approval first).
- **Rejected for now:** option B (Tavily/Exa/Brave) from day one. Not wrong, just extra cost and approval with no proven need yet.
- **Still to verify:** client's key can use the web search tool; per-call price (OpenAI pricing page, not read); Kalshi endpoint paths, settled-market status value and rate limits from official docs.
- **Original proposal and research below (kept for the reasoning):**
- **What the researchers need:** (1) the market itself: question, rules, close date, current price, history; (2) outside evidence with links, so every claim can be cited.
- **Source 1, market data: Kalshi REST API.** Third-party guides (not official docs, I could not load Kalshi's docs page) say market data endpoints are public with no key: list markets, one market, price history candles. WebSocket always needs auth. Official docs must confirm paths, the status value for settled markets, and rate limits (tiered, no numbers found).
- **Source 2, outside evidence, option A: OpenAI web search tool** (Responses API, official docs).
  - Works with the client's existing key, no new vendor. Returns `url_citation` annotations (URL, title) and can list every URL consulted. Domain allow/block lists up to 100 each. `search_context_size` low/medium/high.
  - Limits: Responses API only (Chat Completions only has a search-specific model without filters). 128k search context. No date filter. With `tool_choice: auto` the model may skip searching, so force `required`. Per-call price is on a separate pricing page, not read.
- **Source 2, option B: separate search API (Tavily, Exa, Brave).** Gives us the raw results and page text, so we can store a snapshot for backtests. Cost, latency and quality differ; vendor benchmarks conflict (each vendor tests itself); Brave reportedly removed its free plan Feb 2026. Needs a new account/key and Module 5 approval. No source tested their date filters for leakage.
- **Source 3, domain data:** official sources per topic (e.g. economic releases, sports stats, polls). Depends on market genre, which the client hasn't chosen.
- **Citation rule:** a claim is only kept if it maps to a URL we actually retrieved. Citation checker verifies this.

---

### D8. Frontend (requirements stated, nothing decided yet)
- **User's requirements (2026-10-09):** every page uses the same content width; alignment is clean and consistent; modern visuals; looks polished.
- **Why it matters:** this is what the client sees and where the human approves bets (D2), so it carries trust.
- **DECIDED (user, 2026-10-09):**
  - Pages: market list, prediction detail (probability, reasoning, citations), bet approval, results dashboard (forecast vs Kalshi price vs outcome).
  - Stack: Next.js + React. **Why:** common, large ecosystem, talks to a Python backend over an API. Verified on official docs: Next.js 16.4.0 needs Node >=20.9 (ours is v24.18.0, fine); `create-next-app` is the official generator (Module 8) with TypeScript, Tailwind, ESLint, App Router by default.
  - Look: light and clean (no dark theme for now, less to polish; can add later).
- **DECIDED (user, 2026-10-09): shadcn/ui for components.** **Why:** official CLI `shadcn init -t next` copies components into our project as source files, so we get polished buttons, cards and tables without a heavy UI library. Dependency approval (Module 5) is given for shadcn/ui only; install still waits for the approved spec and must be project-local.
- **Mockups:** user said not yet. Revisit later, before the client demo.
- **Open:** how the frontend talks to the Python/LangGraph backend (API design) and how approval is wired (D2); not discussed.
- **Not built:** no scaffolding until the spec is approved.
- **Mockups made (2026-10-09, user asked to see them; format: HTML file in repo):** `docs/design/mockups.html`, plain HTML/CSS, open in a browser, no install. Four pages (markets, prediction, approval, results) share one width (`--content-width: 1120px`) and one set of tokens. Light theme. All numbers and names ("Forecast desk" is a placeholder) are invented sample data, labeled as such on each page.
  - **One memorable element, the "gap track":** a bar showing Kalshi's price (grey pin) and our estimate (blue pin) with the disagreement shaded. Used small in the market list, large on the prediction page. Chosen because the gap between our estimate and the market is the one thing this product exists to show.
  - **Choices:** Schibsted Grotesk font (loaded from Google Fonts, falls back to system font offline); cool grey-blue palette, not the cream/terracotta default; surfaces only where content needs them; a "paper trading, no orders sent" banner on every page; approval page shows the checks (per-bet limit, daily limit, sources checked, price re-check) and a 10-minute expiry, matching D12.
  - **Checked:** screenshots at 1280px and 390px wide in headless Chrome. Fixed two bugs found that way (page jumped past the header on navigation; odd spacing from tabular numerals on all text). Keyboard focus visible, reduced motion respected. Not tested in other browsers or with a screen reader.
  - **Limits of the mockup:** buttons do nothing; the real build uses Next.js + shadcn/ui and will need empty, loading and error states not drawn here.
- **How we will keep widths consistent (plan):** one shared page layout with a single max-width container used by every page, plus shared spacing and type scale defined once as design tokens.

---

### D9. Milestones (draft for client, `docs/MILESTONES.md`)
- **Order and why:** foundation, research, full pipeline, then **evaluation before the web app**, so we learn whether the system beats the market price before spending effort on polish. Live paper trading, then go/no-go, then optional real bets last.
- **No dates or prices on purpose:** effort is not scoped; any number would be a guess. Add estimates after the spec (M0) is approved.
- **Judgment call to confirm:** I placed the web app (M5) after evaluation (M4). It could run in parallel if the client wants to see screens early; mockups are on hold per D8.

### D10. How we use the Kalshi API (PROPOSED, from what we already know; official docs not re-read this round)
- **Use 1, read market data (M1):** list markets, read one market (question, rules, close time, current price), read price history. Feeds the lead agent and the "market comparer" step. Third-party guides say these REST endpoints need no key; unconfirmed in official docs.
- **Use 2, record outcomes (M4/M6):** read resolved markets to score our forecasts (our own table: forecast, Kalshi price at that time, outcome).
- **Use 3, place orders (M7 only):** authenticated REST (key ID + signed request, per official docs seen earlier). Only after human approval, in its own step (D4 gotcha). Demo environment first; demo and prod keys are separate.
- **Not used:** WebSocket streaming. It always needs auth and we do not need live ticks to forecast; skip until a need appears.
- **Safety:** Kalshi keys are required config, validated at startup, no defaults (CLAUDE.md Module 4). Keys live in project-local env, never in code. Rate limits are tiered and unknown, so we add backoff and log retries visibly.
- **Verified against Kalshi's official docs (2026-10-09; read via search-result summaries of docs.kalshi.com pages, because direct page fetch and curl failed here; pages are some months old, re-check the OpenAPI spec at docs.kalshi.com/openapi.yaml before coding):**
  - **No key needed for reads.** `GET https://external-api.kalshi.com/trade-api/v2/markets` is a plain GET; the market-data quick start says no auth headers for those endpoints. Confirms the third-party claim.
  - **Settled markets:** filter `status=settled` (also `unopened, open, closed, paused`); a settled market's own `status` field reads `finalized`. Timestamp filters `min_settled_ts` / `max_settled_ts`.
  - **Two data tiers:** markets that settled before a "historical cutoff" are NOT returned by `/markets`; use `GET /historical/markets` and `GET /historical/markets/{ticker}/candlesticks`. Read the live cutoff from `GET /historical/cutoff` (do not hardcode). Candle periods: 1, 60, 1440 minutes, with required `start_ts` and `end_ts`. Live route for recent markets: `/series/{series_ticker}/markets/{ticker}/candlesticks`.
  - **Rate limits (token budgets per second, reads):** Basic 200, Advanced 300, Expert 600, Premier 1,200, Prime 4,800. Most requests cost 10 tokens, so Basic is about 20 reads per second. Basic tier comes with signup. Check yours at `GET /trade-api/v2/account/limits`. Numbers may have changed (changelog mentions a 20% increase for higher tiers).
  - **Why it matters to us:** 20 reads per second is far more than we need. Candlestick history lets us record "Kalshi price at forecast time" for backtests. Archived markets need the separate historical routes, so the code must check the cutoff.
- **Still unverified:** exact request/response field names (read the OpenAPI spec when building M1); whether any endpoint we need has a higher token cost.

### D11. Backend to frontend connection (DECIDED 2026-10-09: option B, own FastAPI, and Postgres for all data)
- **Decision:** user chose option B and Postgres. **Why B:** production licensing for option A is unclear (reported enterprise key + Redis) and surprise license cost is a risk on a client project; B uses only free open-source libraries and gives us full control over approval and the order step. **Why Postgres:** LangGraph's checkpointer needs a durable shared store in production (in-memory is per-process), and keeping our own tables (forecasts, outcomes, saved source pages) in the same database avoids running two stores. This **replaces the SQLite assumption in D5**.
- **Dependency approval status (Module 5):** user approved the *choice* of FastAPI + Postgres. Exact packages (FastAPI, a Postgres driver, LangGraph Postgres checkpointer) still to be listed with versions in the spec and checked against Python 3.13 before install. Postgres server itself is a runtime requirement the client must host or provide: **Open: where does it run (client machine, cloud, Docker)?**
- **Original comparison and research below (kept for the reasoning):**
- **Need:** the Next.js app must (1) start a run for a market, (2) show progress while agents work, (3) show the final prediction with citations, (4) let a person approve/reject a bet, which resumes the paused LangGraph run (D2, D4).
- **Option A: LangGraph Agent Server + React `useStream` hook** (`@langchain/react`). Official docs: hook exposes the pending interrupt, resume via `stream.submit(null, {command: {resume}})`, pending approval survives page reload via the thread checkpoint. `langgraph dev` is a local server, no license. **Concerns:** production self-hosting is reported to need a LangSmith enterprise license key plus Redis (sources conflict on free-tier limits and on what the key gates; one forum reading says it only gates observability, unofficial); docs show different stream API versions (`stream.interrupt` vs v3 `stream.interrupts`), so copied code may not match installed versions; ties us to LangChain's server product.
- **Option B: our own FastAPI service around the compiled graph.** Only MIT-licensed libraries. Sources describe: Postgres checkpointer (`AsyncPostgresSaver`) so state survives restarts and multiple workers (in-memory is per-process); `graph.astream(...)` streamed to the browser as Server-Sent Events; `interrupt()` shows up in the stream and we resume with `Command(resume=...)`. **Concerns:** we write the glue (start, stream, resume, reconnect) ourselves; no single source covered the full combination, code sketch is unverified.
- **Proposed endpoints (B):** start run, stream run events, get run result, approve/reject (resume), list/score results. The order step stays a separate node after approval (D4).
- **Design point from me (inference, not sourced):** a multi-agent run is slow and costs money, so it should run as a background job, not tied to one browser request. If the tab closes, the run keeps going and the page reconnects by thread ID. The sources' streaming example is request-bound; reconnect/replay needs extra work.
- **Implication to decide:** the LangGraph checkpointer wants Postgres for production, so our own tables (forecasts, outcomes, snapshots) should probably live in that same Postgres instead of SQLite. Changes the earlier "SQLite" assumption (D5). New dependencies (FastAPI, Postgres driver, etc.) need approval first (Module 5).
- **Verify before building:** `AsyncPostgresSaver` setup details, the `__interrupt__` key in stream output, installed-version stream API, LangSmith/Agent Server license terms (only if we pick A).

### D12. Cost and safety limits (user agreed 2026-10-09 to log as proposed; betting limits are REQUIRED config with no default)
- **Decision:** per-bet, per-day and total-exposure limits are required settings validated at startup; the system refuses to start without them (CLAUDE.md Module 4). **Why:** a conservative-looking default could silently allow bets the client never approved. Cost/search caps (researcher count etc.) may keep safe code defaults, with the client's values set in the spec.
- Everything below is still the proposal; client numbers still open.
**Verified prices (OpenAI pricing page, standard tier, per 1M tokens, input / cached / output):** gpt-5.5 $5 / $0.50 / $30; gpt-5.4 $2.50 / $0.25 / $15; gpt-5.4-mini $0.75 / $0.075 / $4.50; gpt-5.4-nano $0.20 / $0.02 / $1.25. **Web search tool: $10 per 1,000 calls, plus the pages it reads are billed as input tokens at the model's rate.**
**Rough cost per market (MY ESTIMATE, assumed token counts, not measured):** 4 researchers (~50k in, 5k out, ~3 searches each) + 3 forecasters (~20k in, 2k out) + lead/aggregator/checker (~0.2 USD) on gpt-5.4 is about **$1.5 per market**; roughly double on gpt-5.5; much less with mini for some steps. Real numbers come from Milestone 2 tracing. Cost scales with how many markets we run, so a daily market cap matters.

**Layer 1, OpenAI account (hard stop, verified):** a dedicated OpenAI *project* for this system with a monthly **hard spend limit** (Project settings > Limits > Spend, "Enforce a hard limit"). At the cap requests fail with 429 `project_spend_limit_exceeded`. Enforcement is approximate (spend can slightly exceed). Alerts (e.g. 50%/80%) only notify. Only org/project Owners can set it, so **the client must set this, not us**. Hard limits were added July 2026; an older help article saying "soft only" is outdated.
**Layer 2, per-run caps in our code:**
- Max researchers (4) and forecasters (3), max search calls per run (number TBD in spec).
- LangGraph `max_concurrency` (top-level config key) caps parallel workers. `recursion_limit` default is 1000 steps since langgraph 1.0.6, far too loose; set it low. Hitting it raises `GraphRecursionError` we must catch and report.
- A per-run cost/token budget that stops the run: **I found no built-in LangGraph feature for this, so we would count tokens ourselves (unverified, to design in spec).**
- Daily cap on runs, and skip re-running the same market within a set window (TBD).
**Layer 3, betting limits (only matter from M7):**
- Our own checks BEFORE any order: max per bet, max per day, max open exposure. **These are the client's numbers: open.** Per CLAUDE.md Module 4 they are required config validated at startup, no hidden defaults (my reading; confirm).
- Kalshi side (verified): `client_order_id` lets a retry after a network failure be rejected as a duplicate (use it so an order can never double-send, supports D4 gotcha); *order groups* cap contracts matched in a rolling 15-second window and auto-cancel the rest (a contract-count cap, not a dollar cap); `DELETE /portfolio/events/orders` cancels all resting orders (our emergency stop). **Max order size / per-market position limit: not found in docs, check `GET /account/limits` and ask Kalshi.** Use the `/portfolio/events/orders` path; the legacy `/portfolio/orders` is being deprecated.
- **Approval bound to the exact order (my recommendation, no source):** the approval covers market, side, price, quantity; it expires; price is re-checked right before sending and a big move cancels the order and asks again. Stops "approve now, executes later at a different price".
**Layer 4, agent safety (my recommendation, general knowledge):** web pages can contain text that tries to give the AI instructions (prompt injection). Researchers and forecasters get NO order tool; only the order node can trade, and only after human approval, so injected text cannot place a bet.
**Other:** all API keys come from project-local environment settings, validated at startup, never logged or put in traces. A visible kill switch (stop new runs, cancel all resting orders) in the web app.
**Open for the client:** monthly OpenAI budget; allowed models; daily market cap; per-bet / daily / exposure limits.

### D13. Backend language: Python 3.13 (CONFIRMED by compatibility check, 2026-10-09)
- **Why Python:** LangGraph, the OpenAI SDK, LangSmith and FastAPI are all Python-first, and the whole backend design (D3 to D12) is written around them. Local Python is 3.13.11.
- **Checked against PyPI (current releases):**

| Package | Version | Python 3.13 evidence |
|---|---|---|
| langgraph | 1.2.14 | 3.13 classifier listed (3.14 not) |
| langgraph-checkpoint-postgres | 3.1.2 | no classifiers; needs `psycopg` and `psycopg-pool` |
| fastapi | 0.143.0 | 3.13 and 3.14 listed |
| psycopg | 3.3.6 | 3.13 to 3.15 listed; extras `binary`, `pool` |
| langsmith | 0.14.5 | no classifiers; requires >=3.10 |
| openai | 3.26.1 | 3.13 and 3.14 listed |

- **Real test:** a dry-run dependency resolve for Python 3.13 on Linux (`uv pip compile`, in the scratchpad, nothing installed) succeeded for all six together, pulling `langchain-core 1.6.9` and `psycopg-pool 3.3.3`. So there are no version conflicts today. It proves the versions resolve together, not that the code runs; the first real test is Milestone 1.
- **Do not use Python 3.14:** langgraph does not list it.
- **Still needs approval (Module 5) before install:** the package list above goes into the spec; install into a project-local venv only (uv), never globally.

### D14. Client also supplied Kalshi API keys (2026-10-09)
- **What we know:** the client gave Kalshi keys in addition to the OpenAI key. **Not yet known:** demo or production keys; whether tied to a funded real account; what the key can do (read-only vs trade). I have not seen the keys and should not.
- **Effect on plan:** reads (M1 to M6) need no key (D10), so the Kalshi key is only needed for orders (M7) and for checking account limits (`GET /account/limits`). **Until M7, the Kalshi key should not be loaded by the running system at all** (least exposure). Production keys are real money access, so they are treated as the most sensitive item in the project.
- **Handling rules (proposed, CLAUDE.md Module 4):** keys live only in a project-local, git-ignored settings file or the host's secret store; never in code, docs, chat, traces or logs; validated at startup when the feature that needs them is on; demo and production keys kept separate and clearly named. The Kalshi private key is a signing key: the file itself is the secret.
- **If a key was pasted in chat/email/docs anywhere:** treat it as exposed and rotate it before real use.
- **User update:** user has "just an API key" and does not know if it is valid, demo or prod, funded, or its permissions.
- **Verified from Kalshi docs (via search summaries of docs.kalshi.com):** a Kalshi credential is a PAIR: a Key ID plus a private key (RSA or Ed25519; the private key can NOT be retrieved again after creation). Each request is signed (timestamp + method + path, RSA-PSS/SHA-256 for RSA) and sent with headers `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, `KALSHI-ACCESS-SIGNATURE`. **If the client only gave one string (a Key ID) and no private key file, the key cannot be used.** Demo (`external-api.demo.kalshi.co`) and production keys are separate. Keys appear to support scopes (the balance endpoint mentions a `read::portfolio_balance` scope), so a read-only key is likely possible; exact scope list not checked.
- **Safe validity test:** call `GET /trade-api/v2/portfolio/balance` (read-only, returns cents) on demo first, then production. Success = key valid for that environment and shows account balance; auth error = wrong environment, wrong key, or bad signature. Not yet run. A check script needs an RSA/Ed25519 signing library (new dependency, approval first, Module 5), so the plan is to do it in Milestone 1, run by the user locally so the key never enters chat.
- **Open:** demo vs production; scopes (ask client to create a read-only or limited key if possible); who holds the keys long term.

### D15. Many markets, and periodic checks for new signals (client question, user decided 2026-10-10)
- **Client asked:** does it check one market at a time, or several as scheduled for the day?
- **Answer given:** each run analyzes one market in depth (research, forecasts, sources for that market). To cover several, the system works through a list of markets the client chooses (picked in the app, or a daily list). Results show in the app as each market finishes.
- **Added at user's direction:** the system also **re-checks markets periodically for new signals** (new information that could change the estimate), and updates the prediction when it finds one.
- **Not yet decided (needs spec):** how often to re-check; what counts as a "new signal" (a new source, a price move on Kalshi, a data release, or any change); whether a re-check redoes the full pipeline or a lighter one; which markets are re-checked (all listed, or only open ones close to closing); how an updated estimate is shown next to the earlier one; whether a changed estimate re-triggers approval of a prepared bet (should: the old approval covers only the old price and size, see D12).
- **Effects to keep in view (my notes, not told to the client):**
  - Cost: each re-check is another run, so it multiplies D12's per-market cost and uses the daily market cap and the LangSmith 5k trace limit faster. The spec needs a re-check cap.
  - Evaluation (D6): every update is a new forecast. For scoring, we must decide which forecast counts (first, last before close, or each at its own time), and store Kalshi's price at each update time, or the comparison with the market is unfair.
  - Data: our table needs forecast history per market, not one row per market.
  - The scheduling itself (a background job on a timer) is new; it was not in the milestones. Add to the spec, probably Milestone 3 or later.
- **Scheduling was not in the earlier plan.** The client-facing docs (`ARCHITECTURE.md`, `MILESTONES.md`) are not updated yet; update them when the user agrees to scope.

### D16. Client answers and scope changes (user, 2026-10-12)
- **Markets:** client has not said which market types. Stay open, do not design around sports.
- **OpenAI budget / allowed models:** user says do not think about it. Dropped as a planning topic. (D12 per-run caps stay as engineering safeguards, no budget number needed.)
- **Betting limits:** user says do not fixate. Not a blocker; handle at Milestone 7 only. This relaxes the D12 "required with no default" line for now: decide when we reach order placement.
- **LangSmith cloud tracing: consent given** (closes the open risk in D5).
- **Runtime: everything runs in Docker with Docker Compose** (backend, frontend, Postgres together). Closes the "where Postgres runs" question. Docker is the host runtime, not a Python/npm package, so no Module 5 conflict; the spec lists the compose services. Secrets reach containers through env/secret files kept out of the images and out of git.
- **Go-live bar:** user says do not think about it for now. Evaluation (D6) still measures against the market price and a single-AI baseline; the formal go/no-go rule is deferred.
- **Kalshi Developer Agreement:** could NOT be read (page text did not load through the tools here, tried twice). Known only: Kalshi docs say using the API means accepting that agreement, and the agreement describes itself as the terms for programmatic trading. Clauses on bots, limits and liability unread. **Action: user opens kalshi.com/developer-agreement in a browser and pastes the text, or shares it, and I summarize.** Only matters for Milestone 7.

### D17. How to tell a Kalshi key is demo or production (official docs, via search summaries)
- **A key carries no mark.** Docs describe no visual marker in the Key ID (a UUID-style string) or the private key (a PEM file). Environment is set by the account the key was created in.
- **Demo and production are separate accounts and separate keys.** Demo keys only work on demo endpoints, production keys only on production. Demo site: demo.kalshi.co (the .com version is not a Kalshi domain). Demo REST `https://external-api.demo.kalshi.co/trade-api/v2`; production `https://external-api.kalshi.com/trade-api/v2`.
- **Test to run (read-only):** sign a `GET /portfolio/balance` request and send it to the demo host. If it succeeds, it is a demo key. If it fails with an auth error, send the same request to the production host. If that succeeds, it is a production key. If both fail, the key ID or private key is wrong, or the pair is incomplete. Never try an order endpoint to test.
- **Ask the client instead (fastest):** which site they logged into when creating the key (demo.kalshi.co or kalshi.com), under Account & security, API Keys.
- **Scopes:** create-key endpoints take a `scopes` list, but the docs I could read do not list the values. A key can also be limited to one sub-account. Check the scope list in the API reference or in the key dialog.
- **Where the test runs:** a small script we write in Milestone 1, run by the user locally or inside the Docker setup. It needs an Ed25519/RSA signing library (new dependency, needs approval first). Not run yet.

### D18. Approval flow: how the approval screen connects to the paused run (PROPOSED, not yet agreed)
Built only from facts verified in LangGraph docs (D4, D11): `interrupt()` pauses and saves state, resume with `Command(resume=...)` and the same `thread_id`, needs a Postgres checkpointer, the interrupted node re-runs from its start on resume, typed resume validation needs langgraph >= 1.2.12 (we resolve 1.2.14).
1. **Graph ends in three nodes:** `prepare_order` (builds a proposal: market, side, limit price, quantity, estimated cost; saves it to our Postgres table as `pending` with an id and an expiry time), `await_approval` (only calls `interrupt()` with the proposal id, no side effects), `place_order` (separate node, runs only after approval).
2. **Run status in our DB:** running, awaiting_approval, done, failed. `thread_id` = run id.
3. **Web app:** the prediction page shows "Review bet" when status is awaiting_approval. The approval page reads the proposal from OUR table, not from LangGraph state.
4. **Approve/reject endpoint** `POST /runs/{id}/approval` with `{proposal_id, decision}`. The backend checks: proposal exists and is still `pending`, not expired, id matches the one the run is paused on, the caller is allowed to approve. Only then it resumes the graph with `Command(resume={decision, proposal_id})`. A reject resumes the graph to a clean end.
5. **`place_order` rules:** (a) re-fetch the Kalshi price just before sending; if it moved beyond a set tolerance, do not send, mark the proposal `needs_reapproval` and loop back to `prepare_order` through a conditional edge (docs say to avoid a `while True` around `interrupt()`); (b) use the proposal id as Kalshi `client_order_id`, so a retry cannot double-send (D12); (c) in paper mode it records a simulated fill and never calls Kalshi.
6. **Expiry:** the backend refuses an approval after `expires_at` and closes the run with a reject. I have not found an interrupt timeout in the docs read, so expiry is our own check.
7. **Re-checks (D15):** a new estimate creates a new proposal and marks the old pending one `superseded`. An approval for a superseded proposal is refused.
8. **Why this shape:** keeps `interrupt()` side-effect free, so the re-run on resume is harmless; the order step is separate and single-send; the screen shows what the backend will actually send.
- **Open:** **who is allowed to approve.** No login or user model has been discussed. A single-client tool still needs at least a simple sign-in, otherwise anyone who can reach the app can approve a bet. Decide in the spec. Also: price-move tolerance and approval expiry length (the mockup shows 10 minutes as a placeholder).

### D19. Sign-in: simple email and password (user decided 2026-10-12; details PROPOSED)
- **Decision (user):** the app needs a simple login with email and password. **Why:** answers the open point in D18. Without sign-in, anyone who can reach the app could approve a bet.
- **Where auth lives (my recommendation): in the FastAPI backend, not in Next.js.** **Why:** the Next.js docs say to do auth checks "as close as possible to the data source" and not to rely on layouts or the proxy file alone. Our sensitive action (approve a bet) is a backend endpoint, so the backend must check who is calling. One user table, one place to check. **Rejected:** an auth library inside Next.js (e.g. Better Auth, Auth.js): a second user store the backend would have to trust; more parts for one client.
- **How (proposed):**
  - A `users` table in our Postgres (email, password hash, created date).
  - Passwords hashed with Argon2 through `pwdlib` (the library FastAPI's current security tutorial uses; install `pwdlib[argon2]`). Plain passwords are never stored or logged.
  - Login endpoint checks the password (and runs a dummy hash when the email is unknown, as the FastAPI tutorial does, so response time does not reveal which emails exist), then creates a **server-side session**: a random token stored hashed in a `sessions` table with an expiry; the browser gets it as an `HttpOnly`, `Secure`, `SameSite=Lax` cookie. **Why a database session and not a signed token (JWT):** logout and "sign everyone out" work immediately; the FastAPI tutorial's JWT example does not cover revocation. A new package is not needed for this.
  - Every API endpoint (start run, stream, approve, results) requires a valid session. Approve also records WHO approved (user id and time) on the proposal (D18).
  - Next.js pages redirect to the login page when there is no session, but that is only for convenience: the backend check is the real protection.
  - No public sign-up page. Accounts are created by the operator through a backend command. Failed logins are rate-limited.
- **Needs checking before build:** `pwdlib[argon2]` support for Python 3.13 (not yet checked; see D13 method) and Module 5 approval. Cookie `Secure` flag needs HTTPS: fine on `localhost`, but real use needs HTTPS in front of the Docker Compose stack (open: who provides it). Protection against cross-site request forgery for the approve endpoint (SameSite=Lax helps; confirm the exact extra step in the spec). The Next.js guide's own examples (bcrypt, Zod, jose) are for a Next.js-side design and do not apply to this one.
- **Scope decision 2026-10-12 (user): single user, no register page.** The user first asked for a register page and multiple users, then reversed it: the Kalshi key belongs to one client, so keep it simple. **Accounts are created by a script run by the operator** (this is the original D19 design). **Why this is right:** a public register page would let anyone who finds the app approve bets on the client's one Kalshi account and spend their OpenAI budget. Multi-user, roles, invite codes and an admin screen are NOT built. If the client later wants more than one person, add them with the same script.
- **Auth checks done 2026-10-12:** `pwdlib` 0.3.1 lists Python 3.13 and 3.14; `argon2-cffi` 25.1.0 is its dependency. A dry-run resolve for Python 3.13 on Linux succeeded for all seven packages together (langgraph 1.2.14, fastapi 0.143.0, psycopg, langsmith, openai, langgraph-checkpoint-postgres, pwdlib[argon2]). Nothing installed. **New dependency awaiting approval (Module 5): `pwdlib[argon2]`.** No email-validation package planned (pydantic's `EmailStr` needs one; we use a simple check and the unique-email rule instead). No rate-limit package planned; failed-login throttling is done in the database.
- **Project state 2026-10-12:** git repo exists on branch `master` with no commits; `CLAUDE.md` and `docs/` are untracked; no `TODO.md`, no `docs/specs/`, no code.
- **Still open:** password reset is by the same script (no email service); a login page is a fifth page and is not in the mockup or milestones yet; HTTPS in front of Docker Compose for real use.

### D20. Milestone 1 build log (2026-10-12, user said go ahead: approved task list, Alembic with SQLAlchemy, commit per task)
- **Process:** tasks logged in `TODO.md`, spec in `docs/specs/FEAT-20261012-0951-milestone-1-foundation.md`, one commit per task, plus separate bug items for things found while building. The user's "start the work" was treated as spec approval (CLAUDE.md says to wait for explicit spec approval; the user's instruction wins, so the spec was written and work began without a separate sign-off). Commits carry no Claude attribution, per CLAUDE.md. `CLAUDE.md` is git-ignored at the user's request.
- **Done and committed (all `[x]` in TODO.md):** 0951 skeleton and Docker Compose; 0952 database and Alembic migrations; 0953 single-user sign-in; 0954 Kalshi read-only client and market endpoints; 0955 LangSmith tracing check and LangGraph Postgres saved progress; 0956 web app shell; 0957 Kalshi key check command.
- **Bugs found and fixed during the build (own items in TODO.md, specs in docs/specs/):**
  - 0959 login failure counter could be beaten by parallel guesses (reproduced: 12 parallel wrong logins never locked the account); fixed with a row lock.
  - 1000 sessions survived a password change; fixed (password change deletes the user's sessions).
  - 1019 login endpoint could exhaust the server (row lock held while hashing; unlimited parallel hashing); fixed (hash with no lock or connection held, at most 4 password checks at once, extra gets 429).
  - 1029 markets page took 63 seconds to show an error when Kalshi was unreachable; fixed (3 second connect timeout, 3 tries; now about 10 seconds).
  - Three of these came from automated security-review notes on the commits; those notes gave only a category, so the fixes follow what was verified in the code. The latest note ("denial of service in auth.py") arrived after the 1019 fix, and its detail was not visible.
- **Accepted limits (written in the specs):** anyone who knows the email can lock the owner out for 15 minutes by sending wrong passwords; a flood of logins can make real logins return 429 while it lasts; guesses at unknown emails have no throttle. Proper fix is per-IP limits at a reverse proxy when HTTPS is set up.
- **Other root cause found:** LangGraph's table setup uses `CREATE INDEX CONCURRENTLY`, which waits for every other running statement, so several processes starting together deadlocked (and a blocking advisory lock made it worse). Startup now polls with try-lock. Also Alembic's logging setup silently disabled the app's loggers; fixed.
- **Tests:** 62 backend tests pass against the real Postgres in Docker (settings, migrations, sign-in, lockout, concurrency, Kalshi client with mock responses, checkpoint setup, key check). Web app: build and lint pass; checked by hand with a mock Kalshi: sign-in, redirect when signed out, markets list rendered, every page's content width 1120px at the same left edge (390px phone width has no sideways scroll), screenshots reviewed. **There are no automated web app tests yet.**
- **Not verified, because of this environment:** the dev sandbox cannot reach `external-api.kalshi.com`, so the Kalshi client and markets page were never run against the live API; Kalshi's field names (`title`, `close_time`, `last_price_dollars`) come from its docs via search summaries and are shown as a dash if missing. LangSmith tracing was not run (no key). The key check was never run against Kalshi (no key). The first real run on a machine with access should confirm all three.
- **Dependencies added (project-local):** backend: fastapi, uvicorn, sqlalchemy, psycopg, alembic, pwdlib[argon2], langgraph, langgraph-checkpoint-postgres, langsmith, httpx2, cryptography, pytest. Not named earlier in discussion: uvicorn, httpx2 (replaces httpx, deprecated by Starlette), cryptography, pytest. Web app: from create-next-app and shadcn init (includes a package named `cn`). Next.js Cache Components was turned off. Details in the spec, section 9.
- **Local setup:** `.env` (git-ignored) has local passwords and a generated secret; a demo account `demo@example.com` was created in the local Docker database for testing and should be removed or have its password changed before real use. The stack runs on 127.0.0.1 ports 3000 (web), 8000 (backend), 55432 (database for tests).
- **Not done / next:** the Milestone 1 key check run by the user with the client's key; first live Kalshi check; Milestone 2 (research stage). Milestone docs (`MILESTONES.md`) still lack the login page and Docker Compose setup as explicit items; update when convenient.

### D21. Client answers: market types and OpenAI credit (2026-10-12)
- **Market types (client, in chat):** "I mostly do soccer, baseball and tennis." So the client trades **sports** markets. This answers the open market-type question and puts us in the category flagged as legally contested in section 2 (state regulators and appeals courts, as of late Sep 2026). **Client's US state is still unknown** and matters for what they can trade.
- **OpenAI credit:** the client added credit to the OpenAI key. Not verified by us; no key has been shared with the assistant and none should be (it goes in the local `.env`).
- **Effects on the plan (my notes, not yet agreed):**
  - Research angles for these sports are specific: injuries and lineups, recent form, head-to-head, venue or surface (tennis), starting pitchers and weather (baseball), plus the betting odds from sportsbooks as an outside price to compare with Kalshi. The lead agent's planning prompt should be written for these three sports rather than generic.
  - Sports markets resolve in days and facts change fast (lineups are announced close to the start), so re-checks (D15) matter more than for economics markets, and paper-trading results arrive sooner.
  - Sports prices are usually efficient (sportsbooks already set sharp lines), so beating the Kalshi price is likely harder than the general research suggested. The three-way comparison in D6 is more important, not less.
  - Backtests have the leakage problem in D6, especially bad for sports because results are widely published.
- **Open:** client's state; whether the client trades both match winners and other sports contract types (totals, props); approval of the Milestone 2 task list and the three questions asked (page-saving depth, model choice, web app in this milestone).

### D22. Milestone 2 build log: the research stage (2026-10-12; approved by the user with my recommendations)
- **Approval:** the user said "yes, go ahead with milestone 2". Treated as approval of the task list and of my recommendations: save cited pages as link, title and cited claims; `gpt-5.4-mini` planner and `gpt-5.4` researchers; web app included. Spec: `docs/specs/FEAT-20261012-1048-milestone-2-research.md` (deviations in its section 10).
- **Done and committed (`[x]` in TODO.md):** 1048 OpenAI settings, price table and cost; 1049 runs table; 1050 lead agent (sport-aware planner, capped); 1051 researchers (parallel fan-out, claims with real citations); 1052 saved cited pages; 1053 run endpoints (background runs, status, list, guards); 1054 web app (Analyze button, runs list, result page with live progress).
- **What a run does:** planner picks up to 4 angles; one researcher per angle searches the web (forced to search, at most 3 searches, 4000 output tokens each); lines are parsed into claims whose source links come only from the search tool's citations; cost is computed from tokens and searches and shown per run; sources saved; result stored and shown. One active run per market (database rule), at most 2 runs at once, runs cut off by a restart are marked failed at startup.
- **Findings to remember:**
  - OpenAI's citations carry only link, title and position in the answer, no text from the page. So "saved pages" are a record of what each source was cited for, not a page snapshot. A real snapshot needs our own fetch (decide after first backtests).
  - Alembic autogenerate wanted to DROP LangGraph's checkpoint tables; `alembic/env.py` now ignores them, with a test.
  - Starting the app now needs migrated tables; it fails with "run alembic upgrade head" otherwise (compose runs it at start).
  - A hard per-run token stop is not possible with parallel researchers; cost is bounded by per-call caps plus a recorded `over_budget` flag (`RUN_COST_WARN_USD`, default 3.00).
- **Verification done without an OpenAI key:** 124 backend tests (fake model) pass against real Postgres; and a full run through the web app against a mock OpenAI server (the real OpenAI SDK and `OpenAIResearchModel` pointed at it with `OPENAI_BASE_URL`). The cost matched a hand calculation, the request carried the intended settings (forced search, `max_tool_calls`, `store=false`, reasoning effort), duplicates returned 409, and every page kept the 1120px width. Mock servers and mock data were removed afterwards.
- **Not verified (needs the real key; checklist in spec section 9):** any live OpenAI call; that `store=false`, `max_tool_calls` and the reasoning value are accepted; whether annotation indices line up with the text on real answers (out-of-range ones are ignored and counted, never guessed); real cost and time per run (the caps are placeholders to tune); research quality (angles and facts); sportsbook odds appear only if a page shows them. Kalshi live check still pending (D20).
- **Risks and limits:** each "Analyze" or "Analyze again" press spends money and the button does not warn yet; no probability or source checking yet (Milestone 3); cited does not mean verified; the planner prompt is written for soccer, baseball and tennis, so other markets get generic angles.
- **Next:** user puts `OPENAI_API_KEY` in the local `.env` and runs one market live; check the first-live-run list; tune caps from the real cost. Then Milestone 3 (forecasters, aggregation, citation checker, market comparison). Still open from before: client's US state (D21), contract types beyond match winners, the Kalshi key check run, `MILESTONES.md` not yet updated for login and Docker.

### D23. Milestone 3 draft plan: the full prediction (2026-10-12, PROPOSED, awaiting the user's approval; nothing logged in TODO.md or built)
- **Goal:** turn a finished research run into one probability with a visible comparison to Kalshi's price, using only claims whose sources were checked.
- **Pipeline order changed from the architecture table:** research -> fetch and check citations -> forecasters -> aggregate -> compare with the market -> (later) approval. **Why:** unsupported claims should not feed the forecasters; earlier the citation checker came after the aggregator.
- **Proposed tasks (for approval):** (A) settings and data shapes for forecasting; (B) safe page fetching and saving page text; (C) citation checker; (D) forecasters; (E) aggregator; (F) market comparer; (G) wire into the graph, store results and costs; (H) web app: prediction page and the gap column on the markets list.
- **Recommendations and the evidence behind them (all from search summaries, mostly 2026 preprints; verify before relying):**
  - **Forecasters:** 3 independent calls on `gpt-5.4`, same evidence, three different reasoning framings; every individual estimate is stored. Research suggests gains come from agents seeing different evidence (InfoDelphi), so evidence-splitting variants are an experiment for Milestone 4, not assumed.
  - **Forecasters do NOT see the market price.** A benchmark report (AIA Forecaster, citing Karger et al.) found the best LLM forecaster did worse than the market price it was shown (0.109 vs 0.096 Brier), and showing the price can hide weakness. One narrow 2026 study found "price as a prior, then update" helps; that is a Milestone 4 experiment.
  - **Aggregation: median** (simple, robust, used in the "wisdom of the silicon crowd" study). Differences between median and log-odds means were small and within error in ForecastBench (0.197 vs 0.194). No source found on extremizing with only 3 forecasters, so none is applied; spread (min to max) is recorded.
  - **Citation checking has three layers:** structural (a link exists; done), resolvability (the page can be fetched), semantic (the page supports the claim, judged by a model with the page text). The semantic judge has known failure modes (self-preference, length sensitivity), so it is validated against a hand-labelled sample, and results are labelled "supported", "not supported" or "could not check", not just dropped.
  - **Fetching pages ourselves is also the real page snapshot** we could not get from OpenAI's citations (D22), which backtests need. New risks: server-side request forgery (URLs come from a model, so block private and local addresses, limit size, time and redirects), sites that block bots, paywalls, scripts-only pages. An HTML-to-text step may need a new package (to research and ask first).
  - **Market comparer:** compare with the price one could actually trade at (the ask for yes, one minus the bid for no), not the last trade; show the gap and an estimated edge after Kalshi's fee (third-party formula, unverified); flag a gap as "meaningful" only if it exceeds a threshold AND the forecasters agree AND the evidence is not thin. Threshold is a placeholder to tune in Milestone 4.
  - **Evidence rule:** forecasters receive only "supported" claims; if too few remain the run is marked "thin evidence" and says so.
- **Cost (estimate, unmeasured):** adds page fetches, one cheap judge call per claim (`gpt-5.4-mini`) and 3 forecaster calls without search; likely a few tens of cents more per run.
- **Questions put to the user:** order change; fetching pages ourselves; price hidden from forecasters; median; 3 forecasters or 5.
- **Out of scope:** backtests and scoring (Milestone 4), periodic re-checks (D15), approval and orders.

### D24. After Milestone 2: events, fixes and documents (2026-10-12)
- **The OpenAI key and `.env` (user report):** the key was missing from `.env`; `.env` last changed at 09:53, when I created it with a script during Milestone 1 (before any key existed). The user said a redirect/script created or replaced the file and broke their setup. Cause not provable either way; **rule adopted: never create or write `.env` (or any secrets file); edit only `.env.example` and tell the user which line to add.** Saved in memory. The user later added the key; the backend log then showed "Research is ON". Key values are never read or printed; only the presence of the line is checked.
- **Login felt slow (user report) = BUG-20261012-1129, fixed:** login API answered in 0.09 s, but `/markets` showed nothing until Kalshi answered, and the login form asked for the page twice (replace plus refresh), calling Kalshi twice. Fix: the page title and a loading state show at once, the table streams in; one page request; lookups in parallel; sign-out likewise; the backend logs each Kalshi call's duration (`docker compose logs backend | grep "Kalshi GET"`). Measured with a mock Kalshi (1.5 s): title after 0.3 s instead of a blank 1.9 s; exactly one page request and one Kalshi call. The remaining wait is Kalshi's own time, unknown on the user's machine; a short backend cache of the market list is held back until that number is known.
- **Where market data is fetched (user question):** in the markets page itself, on the server, inside a loading boundary; never at login. Alternative (fetch in the browser after render) offered and not chosen.
- **The user may hold the client's Kalshi private key (message cut off):** told not to paste it; how to save it as a file (outside the repo, `chmod 600`) and run `check-kalshi-key` locally with the Key ID; the client's key was sent over WhatsApp, so a fresh key is advised before real trading. **Result of the check: not yet reported.**
- **Kalshi key check result (user, 2026-10-12):** the key is a **production** key, valid and accepted on production (demo rejected it with 401, as expected). The first attempt timed out connecting to production from the user's machine (`ConnectTimeout`); with a **VPN on** it worked. So from the user's location Kalshi's production server is only reachable through a VPN (cause not investigated; Kalshi's regional rules not verified). The user says the VPN is only for development testing and the finished system goes to the client, who runs it from their own location. Consequences: development tests of the markets list and research runs need the VPN on; the backend container follows the host's network (to be confirmed with the connection test); the delivery host must reach Kalshi without a VPN (test from there). The check was read-only (balance request); no balance was printed. The earlier "slow login" may partly have been this connection problem. Risk noted and left to the user and client: using a VPN to reach a US-regulated exchange may conflict with Kalshi's terms; terms unread.
- **Handover checklist (agreed with the user):** (1) the user removes their dev key file and key lines from their `.env`, and does not hand over their `.env`; (2) the client creates a new Kalshi key (limited permissions if offered) and revokes the one shared over WhatsApp; (3) replace the demo account with a real one made by the script; (4) the client's own `.env`: their OpenAI key, new `SESSION_SECRET` and database password, `SESSION_COOKIE_SECURE=true` once HTTPS exists, LangSmith if wanted; (5) test that the host reaches Kalshi without a VPN; (6) read Kalshi's Developer Agreement before any real order.
- **First look at live Kalshi data (user's PDF, VPN on, 2026-10-12) = BUG-20261012-1310, fixed:** the connection works and real markets load, but the list was full of **combination (multi-leg) markets** ("yes Name, yes Name, ...") with price 0%. Cause: Kalshi's Get Markets returns multivariate markets unless `mve_filter=exclude` is sent (documented parameter; values `only` and `exclude`), and our page printed a zero last price as "0%". Fix: the backend defaults `mve_filter` to `exclude` (the endpoint accepts `only` too, other values are refused); the page shows "No trades yet" for a zero or missing price (a traded contract cannot have a last price of zero). Checked against a mock Kalshi (parameter sent, three price cases rendered); not re-checked against the live API from my side. **Not done:** a sports-only list (Get Markets has no category filter in the docs read; categories live on events, so it needs the events endpoint and its field names), ordering, paging beyond the first 50, showing bid and ask. Next time the user opens the page the list should show single markets; the user is asked to confirm.
- **Sports-only filter: what Kalshi's docs say (research only, nothing built; search summaries of docs.kalshi.com, 2026-10-12):**
  - `GET /markets` has `mve_filter`, `series_ticker`, `status` (one of unopened, open, closed, settled), `tickers`, close and settle time filters, `limit` (default 100, max 1000) and `cursor`. **No category or tag filter.**
  - `GET /events` (excludes combination events by default) has `series_ticker`, `status`, `with_nested_markets`, `min_close_ts`, `limit` (default 200) and `cursor`; each event carries a `category` field, but **no category filter** was found.
  - **The category filter is on `GET /series`:** `category=Sports` and `tags=Tennis,Baseball,...` (comma separated), returning series tickers. `GET /search/tags_by_categories` lists the tags per category (built from series that currently have open markets); `GET /search/filters_by_sport` lists sports with their competitions and scopes. The exact tag values for soccer, baseball and tennis were not found (the docs' example uses Tennis and Baseball).
  - **Consequence:** a sports-only list is two steps (find sports series, then fetch their markets, one series per call because `series_ticker` takes a single value), not one call. How many series there are (leagues, game, totals, spreads) is unknown, so the cost in calls and time is unknown.
  - **Options:** (A) series-first: cache the sports series list for an hour, fetch open markets for those series in parallel with a cap, merge and sort by close time (accurate, many calls); (B) events-first: page through open events with nested markets and keep those whose `category` is Sports (few code paths, unknown page count); (C) keep the unfiltered single-market list and add search and paging so the user picks markets by hand (simplest, no category dependency). Decision waits for three harmless public calls the user runs with the VPN on (tag values, series count, a sample) to size the problem.
- **Demo login for local testing** was given to the user (`demo@example.com`, local Docker database only); to be replaced by a real account made with `python -m app.cli create-user` before real use.
- **Milestone 3 draft** presented (D23); awaiting approval. The user asked for a document explaining the graphs: written as `docs/agent/GRAPHS.md` (Built versus Planned labels, parallel versus sequential for every step, settings, where to change things).
- **Documents brought up to date:** `docs/ARCHITECTURE.md` and `docs/MILESTONES.md` rewritten for the client to match reality (sports focus; what is built and what is not; Docker and sign-in; "Cited" does not mean "checked"; cited-text limitation; the Milestone 3 order change; go-live rule deferred; periodic re-checks proposed). Memory files updated (project state, working preferences).
- **Commit history:** every task and bug is its own commit on `master` (no remote connected when last checked); `TODO.md` is up to date; no Claude attribution in commit messages, per CLAUDE.md; `CLAUDE.md` is git-ignored at the user's request.

### D25. Live Kalshi facts for sports markets (measured 2026-10-12 with the VPN on, public calls only, no key)
- **Why this entry:** the user asked to "check for the filter first"; I called Kalshi's public endpoints myself (the build machine is the user's laptop and the VPN was on). These replace several earlier guesses.
- **Sports tags exist:** `Soccer`, `Baseball`, `Tennis` (plus Football, Basketball, Hockey, MMA, and more) in `GET /search/tags_by_categories`. `GET /search/filters_by_sport` returns competitions and scopes (names only, no series tickers); scope "Games" is the match markets.
- **Series counts (`GET /series?category=Sports&tags=X`):** Soccer 1,415, Baseball 230, Tennis 143. Each call took 5 to 12 seconds on the VPN. Fetching markets series by series for all of them is not workable (thousands of calls).
- **Events-first is not workable either:** `GET /events?status=open&with_nested_markets=true&limit=200` pages are 2 to 5 MB and took 8 to 16 s each; 8 pages (1,600 events, 107 s) were not the end, and sports were a small share (the order is not by sport).
- **What works: single-match series follow a naming pattern** (`...GAME` and `...MATCH`): e.g. `KXEPLGAME`, `KXUCLGAME`, `KXMLSGAME`, `KXLALIGAGAME`, `KXSERIEAGAME`, `KXMLBGAME`, `KXNPBGAME`, `KXKBOGAME`, `KXATPMATCH`, `KXWTAMATCH`, `KXATPCHALLENGERMATCH` all returned real open markets. 149 soccer, 12 baseball and 35 tennis series look like game or match series (too many to query live; a curated list is needed). 11 series fetched 6 at a time took 9.9 s wall on the VPN (each 2.4 to 5.3 s), 620 open markets in total.
- **Timing context:** one tiny call took 3.2 s on the VPN (1.6 s just to connect). This explains why the first check hit the 3 s connect limit and why the markets page waited seconds; from the client's own network it is likely faster (unmeasured). The backend's connect timeout (3 s) is tight for a VPN.
- **Market fields now verified from live data:** `ticker`, `title`, `yes_sub_title`, `no_sub_title`, `event_ticker`, `status`, `close_time`, `open_time`, `occurrence_datetime`, `expected_expiration_time`, `last_price_dollars`, `yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars`, `volume_fp`, `open_interest_fp`, `volume_24h_fp`, `rules_primary`, `rules_secondary`, `result`, `market_type`. There is **no `subtitle` field** (our code reads one; it is never filled). Event objects have `title`, `sub_title`, `series_ticker`, `category`, `event_ticker`, `markets`.
- **What a sports market looks like:** one market per outcome of a game, not one per game. A soccer game has three markets (home wins, "Tie is the result", away wins), titled like "Newcastle wins", all sharing one `event_ticker` (for example `KXEPLGAME-26OCT25CRYNEW`). The game name ("Crystal Palace vs Newcastle") is on the event, not the market; `rules_primary` carries the full description (our researchers receive it). **`close_time` is when trading closes (days after kickoff in the samples), not the game time; `occurrence_datetime` is the game time.**
- **Prices:** `last_price_dollars` is `0.0000` on many markets that have a bid and an ask (for example Tie: bid 0.25, ask 0.28). So the earlier fix that shows "No trades yet" for a zero last price is misleading for these; the tradeable price is bid and ask. Some spreads are huge (bid 0.05, ask 0.69): thin markets.
- **Options now (decision pending with the user):** (A') a curated list of series (setting, default = the major leagues and tours above, the client chooses), fetched per series through events (richer: game title and all outcomes) in parallel with a cap, cached about a minute, grouped one row per game; (C) keep the unfiltered single-market list with search and paging. Recommended: A'. Open design question: run research once per game (outcome markets share the research) or once per outcome market (three runs per soccer game, three times the cost). Recommended: per game, so one run feeds forecasts for every outcome in Milestone 3.

### D26. Sports games list and research per game: built on branch `feature/sports-games-list` (2026-10-12, user approved the plan from D25 and asked for a separate branch)
- **Decision (user):** option A' from D25: a configured league list, one row per game, buy and sell prices, game start time, longer connect timeout, and **one research run per game** (not per outcome). The user asked for a separate branch; branch created by me on their instruction (`feature/sports-games-list`, base `master`, not merged, no remote). Spec: `docs/specs/FEAT-20261012-1426-sports-games-list.md`; tasks 1426 to 1430 in `TODO.md`.
- **Why:** Kalshi has no one-call sports filter (D25). A short list of single-match series gives a fast, accurate list; per-game research costs a third as much for soccer (three outcomes) and half for tennis and baseball, and one run can feed every outcome in Milestone 3.
- **What was built (all tested, 150 backend tests pass; web app lint and build pass):**
  - Kalshi client: `list_events`, `get_event`; timeouts connect 6 s, read 20 s (a VPN connection took 1.6 s and an events page 5 s); worst case for an unreachable Kalshi about 20 s.
  - Games list: setting `SPORTS_SERIES` (`Sport:TICKER:League`, default 15 series each checked live to have open games: EPL, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, NPB, KBO, ATP, WTA, ATP and WTA challenger), `GAMES_CACHE_SECONDS` (60) and `SPORTS_FETCH_CONCURRENCY` (6); parallel fetch with a cap, one lock so simultaneous loads share one refresh, a failed league is reported on the page and the result is kept only 10 s, `GET /api/games?sport=&q=&limit=&include_started=`. Live check: 335 games, 5 s first call, 11 ms cached.
  - Research per game: runs table columns renamed to `event_ticker` and `event_title` (migration; the `forecasts` table keeps `market_ticker` because forecasts will be per outcome market); the agents get the game title, detail, start time, the list of outcomes and the rules text, never prices; `POST /api/runs` takes `{event_ticker}` and fetches the event itself; one active run per game.
  - Games page at `/games` (`/markets` redirects): one row per game, start time in the viewer's time zone, each outcome with its sell and buy price in cents, sport filter, search, per-game Research button, errors per league, a loading state, a two-column layout on phones; page width unchanged (1120 px).
- **Findings along the way:** (1) games that already started stay open on Kalshi until they settle, and sorted first (some 30+ hours old), so they are hidden by default with a "Show started games" link (spec updated); (2) the earlier "No trades yet" label was misleading for markets with a zero last price but real bids and asks, so the page now shows bid and ask and does not use the last price; (3) a first version of my own test used the decoded URL path and did not prove the path-escaping, fixed to check the raw path; (4) I committed once with one failing test because my command did not stop on failure, then fixed and amended before anything was shared.
- **Verified live (public calls, VPN on, no OpenAI spend):** all 15 default series return open events; `GET /events/{ticker}` returns the markets at the top level; a real game ("Atalanta vs Venezia") run end to end with a mock OpenAI: the agents received the game, start time, all three outcomes and the full rules text, no prices; a second press returned 409; page timings and widths on 1280 px and 390 px.
- **Not verified:** research quality and cost on the real OpenAI API (still the user's first live run); behaviour on the client's own network (the 5 s first refresh is the VPN's); that the default league list matches what the client trades; totals, spreads and props are not shown (only game and match winners); game times near midnight and across time zones were checked only visually for the user's own zone.
- **Left over from before and still present:** `GET /api/markets` and `/api/markets/{ticker}` (single-market endpoints, now unused by the web app; protected by sign-in; remove when convenient); the Prediction page still lists runs by game title; the run result page says "game".
- **Next:** the user runs one real game with the OpenAI key and reports cost, time and results; the user decides whether to merge the branch; the client confirms leagues and contract types; then the Milestone 3 plan (D23) needs approval, and it should now be read per game (one probability per outcome of the game).

### D27. First real research run (2026-10-12, the user chose "run one real research"; real OpenAI key, live Kalshi, VPN on)
- **Run:** Atalanta vs Venezia (Serie A, same day), run `3833f5bb...` via `POST /api/runs` with the event ticker. **Result: done, no errors, about 37 s of run time (46 s from the press to done), cost $0.3216, 56,109 input and 5,398 output tokens, 11 web searches, 4 angles, 22 claims all with citations, 0 citations ignored as out of range.** The run record is still in the local database.
- **Now confirmed on the live OpenAI service (were unverified):** `store=false`, forced search (`tool_choice=required`), `max_tool_calls` (11 searches across 4 researchers, none above 3 each), reasoning effort `low`, the web search tool, structured planner output, and citation positions that line up with the text. Cost is far below my estimate (about $1.50 per market) and the run is far faster than expected (estimated minutes). Cost and time per game are therefore small; there is room to raise `MAX_SEARCHES_PER_RESEARCHER` if the research benefits (not yet tried).
- **Research quality, honest reading (a first sample, one game):**
  - Useful: official club and league pages for squad lists, fixtures and previews; head-to-head with dates and scores; the planner chose four sensible angles for a soccer game.
  - Weak: low-value padding lines (for example "the league page showed no data"); **kickoff times disagree between sources (16:30, 18:30 and Kalshi's 19:30 UTC)**; the only betting odds found came from a page "crawled two weeks ago", so there are **no current odds**; some derived claims (days of rest) are the model's own arithmetic cited to pages that do not state them; the fourth angle mixes venue, rest and odds. "Cited" is not "supported", which is what the Milestone 3 source check is for.
  - Presentation bug: 16 of 22 claims contain literal `**` bold markers, shown as asterisks on the result page (logged as BUG-20261012-1449). Quality issues logged as ISS-20261012-1450. Neither is fixed yet (the user chose only the real run).
- **Other timings seen:** `GET /events/{ticker}` took 2.8 s on the VPN; a games-list refresh took 4.8 s for 15 series, 333 games, no failures.
- **Next options for the user:** fix the asterisk bug and tighten the researcher instructions (plain text, only informative facts, one topic per angle, state the date of odds, no derived arithmetic); try a few more games (soccer, baseball, tennis) to see how consistent the quality is; then plan Milestone 3 per game (D23, D26).

### D28. Researcher instruction change checked with real runs (2026-10-12, ISS-20261012-1450 and BUG-20261012-1449)
- **Compared:** the first soccer run (old instructions) against three runs with the new instructions: the same soccer game, an MLB playoff game (Dodgers vs Brewers) and an ATP match (Hurkacz vs Davidovich Fokina). All done, no errors.

| | Soccer before | Soccer after | Baseball after | Tennis after |
|---|---|---|---|---|
| time | 37 s | 28 s | 48 s | 35 s |
| cost | $0.32 | $0.26 | $0.33 | $0.30 |
| searches | 11 | 9 | 12 | 9 |
| claims (cited) | 22 (22) | 21 (21) | 22 (17) | 19 (19) |
| lines with `**` | 16 | 0 | 0 | 0 |
| padding-style lines | 1 | 0 | 1 | 0 |
| betting odds | two weeks old | dated 23 to 50 minutes old, several books | dated 6 minutes old, three books | dated, 16 books compared |

- **Result:** markdown gone; odds are now current and dated; padding almost gone; no rest-day arithmetic; the researchers now say plainly when sources disagree about the start time. One run (baseball) had 5 uncited lines (four recent postseason results with no source link and one start-time note). Costs stayed $0.26 to $0.33 and runs under a minute.
- **Still open:** "cited" still does not mean "supported" (Milestone 3); sample is four runs.
- **Finding that came out of the disagreeing start times (BUG, see D29):** the start time we show and give the agents is wrong.

### D29. Wrong game start times found and fixed: `occurrence_datetime` is settlement time (2026-10-12)
- **How it surfaced:** in the comparison runs (D28) the researchers wrote that sources gave a different start time from the one we told them (we said 19:30 UTC, the league said 16:30).
- **Verified cause:** the markets' `occurrence_datetime` equals `expected_expiration_time`: the expected settlement time. Against milestones (`GET /milestones`, needs `limit`): Atalanta vs Venezia milestone 16:30 UTC vs 19:30 (3 h late); Dodgers vs Brewers game 2 milestone 21:00 UTC (5 p.m. ET, as MLB says) vs 03:00 next day (6 h late); Hurkacz vs Davidovich Fokina milestone 11:10 vs 07:00 (4 h early). So the Games page "Starts" column, the "started" hiding and the agents' "Starts:" line were all wrong. (This corrects D26 and D25, which treated `occurrence_datetime` as the game time.)
- **Fix (BUG item in `TODO.md`, spec `docs/specs/BUG-...-wrong-start-times.md`):** the games list takes kickoff from one bulk milestones fetch (Sports, 48 hours back, all pages, mapped by every listed event ticker, cached 10 minutes, parallel with the series, own worker); no milestone means no start time (shown "–", sorted last), never a guess; a failed fetch gives null starts plus a note on the page and a retry after 10 s; a run start fetches the milestone for its event and gives the agents "Scheduled start (exchange)" only when known. A test also caught that my first version let 5 series run at once with a limit of 4; fixed with a separate worker for start times.
- **Verified live:** 334 of 334 games have a start time; the three samples match their milestones; first call after a restart 10.6 s on the VPN (series and start times together), repeats 8 ms. 169 backend tests pass.
- **Also learned (not used yet):** a milestone's `primary_event_tickers` lists every market type for the same game (winner, spread, totals, both-teams-to-score, halves; player props for baseball), which will matter if the client wants more than game winners.
- **Not verified:** whether every league in the default list has milestones at all times (all 334 games did today); behaviour from the client's own network.

---

### D30. Milestone 3 started: page fetching built, Jina Reader measured and NOT adopted (2026-10-12)

- **What was built:** the data shape (migration `4861f4eda80a`) and the safe page fetcher (`backend/app/research/fetch.py`): public addresses only, connection pinned to the checked address, every redirect re-checked, size and time limits, text only, every outcome recorded. Not yet wired into a run (task FEAT-20261012-1628).
- **Measured, plain fetch, 46 pages from the four real runs:** 37 ok, 8 HTTP 403 (bot blocking: atptour, betmgm, oddschecker, reutersconnect, rotascore, worldfootball, it.wikipedia), 1 no DNS (an image host), 0 JavaScript-only.
- **Measured, Jina Reader (official `oss` image, local) on the 23 non-ok or short pages:** only 1 of the 9 failed pages was really recovered (it.wikipedia, 75k characters). Four bot-wall pages (atptour, oddschecker x2, worldfootball) came back as **HTTP 200 with a "Performing security verification" text of about 260 characters**, which an automatic pipeline would take for page content. One timed out (betmgm), one was "Your request was blocked" (rotascore), reutersconnect returned a stub. The short "ok" pages (Lega Serie A, Venezia, Atalanta) gave 2 to 7 times more text, but it begins with menus and navigation, so the gain in real match facts is unproven. Time: 10 to 49 s per page (plain fetch: 2 to 7 s), on a 2-CPU, 3 GB container through the VPN. Image size 3.3 GB.
- **Decision:** do not add Jina now. Reasons: it fixes about one blocked page in nine, takes 5 to 10 times longer, adds a 3.3 GB browser container plus the egress proxy it would need to be safe (its docs have no option to block private addresses), and turns bot walls into fake successes. This follows the stop rule agreed before the test ("if Jina recovers few pages or is slow, keep the plain fetcher").
- **Rejected:** Jina as a fallback (above); a headless browser we run ourselves (same weight and safety cost, no evidence it passes the bot walls); a paid page-reading service (sends every URL to a third party).
- **What it means for the pipeline:** claims cited only to pages we cannot read are labelled "could not check", stay visible, and do not go to the forecasters. About one cited page in five is lost this way, and it is disproportionately odds and tennis sites. The claim checker (next) must also treat a menu-only page as "could not check", not as "not supported".
- **Revisit when:** the claim-check results show too many lost claims on pages that matter, or PDFs turn up often (none in the 46 sampled). Then reconsider a reader service, with the egress proxy.
- **Where:** `docs/specs/FEAT-20261012-1620-milestone-3-prediction.md`; raw comparison kept only in this note (the data was read from the local database, nothing was written to it).

### D31. Claim checker measured on a labelled sample: safe, but loses most true claims (2026-10-12)

- **What was built:** the checker (`app/research/check.py`: one call per page, verdict kept only with a quote verified on the page the judge saw, safe default `could_not_check`) and a labelled sample of 25 cases with a scoring command (`app.research.score_checker`, about 3.5 cents).
- **Result with the real judge (`gpt-5.4-mini`):** 0 of 25 wrongly marked `supported` (including a page that tried to give the judge instructions); only 2 of 9 true claims kept as `supported`. Causes: the "all numbers of the claim in the quote" rule drops publication dates (3 cases); quotes the judge stitched from separate passages are not found on flattened pages (2); the judge misread a flattened table and called two correct claims `not_supported` (2); plus run-to-run variation. Cost about 1.4 cents per page.
- **What matters:** only `supported` goes forward, so false `supported` must stay at zero and recall is what we tune; `not_supported` against `could_not_check` is a display difference.
- **Caveat:** the labels were written by the assistant and need a person's spot-check (one of my labels was wrong and the judge right).
- **Next:** ISS-20261012-1729 (multi-quote, table hint, re-measure). The alternative is to check the claim's numbers against the page instead of the quote.
- **Where:** `docs/specs/FEAT-20261012-1620-milestone-3-prediction.md` (task 4 result, label table), `backend/tests/data/claim_labels.json`.

## 4. Environment
Python 3.13.11, Node v24.18.0, uv 0.9.5. No project code yet. CLAUDE.md rules apply: project-local installs only, ask before adding any dependency, spec and approval before code.

---

## 5. Not decided yet (so no one assumes)
- **Milestone 3** (D23), now **per game**: the task list for approval; the five questions (check sources before forecasting; fetch pages ourselves with safety limits; hide the price from forecasters; median; 3 or 5 forecasters); one probability per outcome of a game; how "meaningful gap" is defined.
- **Merging `feature/sports-games-list`** into `master`: the user's call.
- **Which leagues and bet types the client trades** (default list of 15 series; only game and match winners shown; milestones list spreads, totals, halves and props for the same game if wanted later, D29).
- **Periodic re-checks** (D15): proposed, client not asked.
- **Approval flow details** (D18): built in a later milestone. HTTPS for real use.
- **Dropped by the user for now (D16):** OpenAI budget and models, betting limits (until the order milestone), the go-live rule.

---

## 6. Questions for the client
1. Which US state are they in? (Not answered; matters for sports contracts.)
2. Which leagues and tours exactly, and only game and match winners, or also totals, spreads and player props? (The Games page shows 15 series by default, D26.)
3. Do they want periodic re-checks for new information (D15)?
4. What should "help" cover: finding and researching bets, or also sizing? (Not answered.)
5. Will they create a new Kalshi key (limited permissions if offered) and revoke the one shared over WhatsApp? (D24 checklist.)
Answered: soccer, baseball and tennis (D21); LangSmith cloud tracing OK; Docker Compose; OpenAI credit added; the Kalshi key is production and valid (D24).

## 7. Next steps
- **Me, when the user says go:** the Milestone 3 plan per game for approval (D23 revised), then spec and build with a commit per task on a branch the user names.
- **User:** decide when to merge `feature/sports-games-list`; ask the client the questions above; optionally press Research on more games and report quality.
- **Small, anytime:** remove the unused single-market endpoints (`/api/markets`); a cost note on the Research button; automated web app tests; a run guide for the operator; show totals and spreads if the client wants them.
- **Before any real order:** read Kalshi's Developer Agreement (could not be loaded, D16), rotate the shared key, agree betting limits and the go-live rule; handover checklist in D24; test that the host reaches Kalshi without a VPN.
