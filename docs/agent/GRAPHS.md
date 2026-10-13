# Agent graphs: how a run works

This document explains every step, agent and branch of the research system: what each one does, what runs in parallel and what runs one after another, what each is for, and how it is used.

**Status labels used throughout**
- **Built**: exists in the code today (Milestones 1 and 2), tested, and checked end to end with a mock OpenAI server. Not yet run against the real OpenAI API.
- **Planned**: agreed direction or proposal, **not built**. Milestone 3 steps are a proposal still waiting for approval (`docs/discussion/NOTEPAD.md`, D23). The approval and re-check steps are designs from earlier discussion (D15, D18).

Code lives in `backend/app/research/` (graph, model calls, prompts, claims, pricing, sources, runner) and `backend/app/runs.py` (endpoints).

---

## 1. The big picture

A **run** is one research job for one **game** (a Kalshi event, for example "Coventry vs Newcastle", with all its outcomes). A person presses *Research* on the Games page; the backend records a run and works on it in the background; the person watches the result page fill in.

```
 Browser: press "Analyze"
        │  POST /api/runs {ticker}
        ▼
 ┌─────────────────────────────  Backend (FastAPI)  ───────────────────────────────┐
 │ 1. checks: logged in, research on, not too many runs, no active run for the game │
 │ 2. fetch the game (event) from Kalshi (server's own copy)                        │
 │ 3. insert run row (status "queued")  ──► answer 202 immediately with the run id  │
 │ 4. start a background task ───────────────────────────────┐                      │
 └───────────────────────────────────────────────────────────┼──────────────────────┘
                                                             ▼
                                         ┌──────────  THE RESEARCH GRAPH (LangGraph)  ──────────┐
                                         │  plan  ──►  research ×N (in parallel)  ──►  end      │
                                         └──────────────────────────────┬────────────────────────┘
                                                                        ▼
                         runner: total tokens and cost, save sources, status "done" or "failed"
        ▲
        │  the page asks GET /api/runs/{id} every 3 seconds while the run is active
 Browser: result page
```

Two layers, kept apart on purpose:
- **The graph** (LangGraph) holds the thinking steps: plan, then research. It knows nothing about the database or the web.
- **The runner and endpoints** hold everything around it: who may start a run, limits, saving results, failure handling.

---

## 2. The research graph (Built)

### 2.1 Shape

```
            START
              │
              ▼
        ┌───────────┐
        │   plan    │   LEAD AGENT (planner)           ← sequential: runs first, alone
        └─────┬─────┘
              │  one "Send" per angle (up to MAX_RESEARCHERS)
     ┌────────┼────────┬────────┐
     ▼        ▼        ▼        ▼
 ┌────────┐┌────────┐┌────────┐┌────────┐
 │research││research││research││research│  RESEARCHER AGENTS  ← parallel: all at once
 └───┬────┘└───┬────┘└───┬────┘└───┬────┘
     └─────────┴────┬────┴─────────┘
                    ▼   results merged by list "reducers"
                   END   (the graph ends only when every researcher has finished)
```

### 2.2 The shared state

All steps read and write one state object (plain data only, because it is saved in the database):

| Field | Meaning | Written by | How combined |
|---|---|---|---|
| `game` | the game being researched (event ticker, title, detail line, start time, outcome labels, rules text; **no prices**) | the runner, at the start | fixed |
| `angles` | the research angles after the cap is applied | `plan` | set once |
| `cut_angles` | how many proposed angles were dropped by the cap | `plan` | set once |
| `findings` | one entry per researcher that produced findings | each `research` | **appended** (reducer: add lists) |
| `usages` | token and search counts for every model call (planner and each researcher) | `plan` and each `research` | **appended** |
| `errors` | one entry per researcher that failed | each `research` | **appended** |

The *append* rule is what lets four researchers write to the same fields at the same time without overwriting each other.

### 2.3 Node `plan`: the lead agent

| | |
|---|---|
| **Kind** | LLM agent, one call |
| **Model** | `PLANNER_MODEL` (default `gpt-5.4-mini`), no web search |
| **Runs** | first, alone (sequential) |
| **Input** | game title, detail line, scheduled start (from the milestone, left out when unknown), the list of outcomes (for example "Newcastle wins; Tie is the result; Coventry wins"), rules text, today's date. **No prices.** |
| **Output** | a structured list of angles; each has a short `name` and a specific `question` |
| **Use case** | decide what is worth looking into for *this* game, so research is focused instead of generic |
| **How it is used** | its angles decide how many researchers start (one per angle) and what each is asked |

What it is told (see `prompts.py`):
- Return between 2 and `MAX_RESEARCHERS` angles, each answerable from web pages with names, dates and numbers.
- Never state an outcome or a probability.
- For soccer, baseball and tennis (the client's markets), pick from: injuries/suspensions/lineups (probable pitchers in baseball); recent form; head-to-head; venue, travel, rest and schedule (surface for tennis, weather and ballpark for baseball); and the current sportsbook odds as an outside price. For anything else, use general angles: latest news, official rules and data sources, base rates.

Rules the code enforces after the call:
- More angles than `MAX_RESEARCHERS`: the extra ones are dropped, the drop is logged and recorded in `cut_angles` (shown on the result page).
- Zero angles: the run fails with "The planner returned no research angles".
- The planner call's token usage is recorded (and paid for) even though it uses no search.

Settings that shape it: `PLANNER_MODEL`, `RESEARCH_REASONING_EFFORT` (default `low`), `MAX_RESEARCHERS`. The planner's output limit reuses `RESEARCHER_MAX_OUTPUT_TOKENS` (4000), one shared setting.

### 2.4 Edge `fan_out`: how "spawning" works

LangGraph has no "spawn" call. After `plan`, a function returns one `Send("research", {game, angle})` per angle. LangGraph starts one `research` step for each, **at the same time**, each with its own small input. The graph moves on only when all of them are done. A cap on simultaneous steps (`max_concurrency = MAX_RESEARCHERS`) is set in the run configuration.

### 2.5 Node `research`: the researcher agents

| | |
|---|---|
| **Kind** | LLM agent with web search; one instance per angle |
| **Model** | `RESEARCHER_MODEL` (default `gpt-5.4`) |
| **Runs** | all researchers **in parallel** (up to `MAX_RESEARCHERS`); each starts only after `plan` finished |
| **Input** | the same game description, plus the angle's name and question and today's date. **No prices** (so researchers are not anchored by the market). |
| **Tool** | OpenAI web search, forced (`tool_choice = required`; with "auto" the model may skip searching), at most `MAX_SEARCHES_PER_RESEARCHER` (default 3) searches, medium search context |
| **Limits per call** | `RESEARCHER_MAX_OUTPUT_TOKENS` (default 4000, includes reasoning), `RESEARCH_REASONING_EFFORT` |
| **Privacy** | `store = false`, so OpenAI is asked not to keep the response |
| **Output** | 3 to 6 findings as text lines, each starting with `- `, each one specific fact with the date of the information when the page gives one; or the single line "No relevant information found." |
| **Use case** | gather facts about one angle, with links, for later steps and for the reader |
| **How it is used** | its lines become **claims**; claims with sources are what the page shows (and what Milestone 3 will check and forecast from) |

It is told never to write a probability, a prediction or a betting recommendation.

**From text to claims** (`claims.py`): the answer text and OpenAI's `url_citation` annotations are turned into claims:
1. Only lines starting with `- ` count.
2. Each line's sources are the citations whose position falls inside that line. **Links come only from the search tool's citations, never from URLs the model typed.**
3. OpenAI also writes each citation as link markup inside the text; that markup is cut out of the claim text and kept as structured sources.
4. Each claim gets a kind: `sourced` (has a citation), `uncited` (no citation on the line), or `none` (the researcher found nothing).
5. A citation position outside the text is ignored and counted (`ignored_citations`); positions are never guessed.

**Failure handling** (one researcher never takes the others down):
- A model or API error for one angle becomes an entry in `errors` and the other angles carry on.
- An unexpected crash in one researcher is caught, logged in full, and recorded the same way.
- An answer with no findings is recorded as an error ("The answer contained no findings") but its tokens are still counted, because the call was paid for.
- If every researcher fails, the run ends `failed`; if at least one produced findings, the run is `done` and the failed angles are listed under "Angles that did not finish".

### 2.6 What is parallel and what is sequential inside the graph

| Step | Relationship | Why |
|---|---|---|
| `plan` → researchers | **sequential** | researchers need the angles |
| researcher 1, 2, 3, 4 | **parallel** (cap `MAX_RESEARCHERS`) | angles are independent; parallel keeps a run to about planner time plus the slowest researcher |
| all researchers → end | **join** (wait for all) | the result is only complete when every angle has answered |

Total money is the **sum** of all calls; total waiting time is roughly the planner plus the **slowest** researcher, not the sum.

---

## 3. Around the graph: the runner and endpoints (Built)

### 3.1 Starting a run (`POST /api/runs`), in order

All of these happen **sequentially, before the graph starts**, and any one can refuse the request:

| # | Check or action | Refusal |
|---|---|---|
| 1 | signed in, and the `X-Requested-With` header present | 401 / 403 |
| 2 | research is configured (OpenAI key present) | 503 "Research is not configured" |
| 3 | fewer than `MAX_CONCURRENT_RUNS` (default 2) runs active | 429 |
| 4 | reserve a run slot (before any waiting, so parallel clicks cannot overshoot) | |
| 5 | fetch the game from Kalshi with `GET /events/{event_ticker}` (the server's copy, not what the browser sent) | 404 "Game not found" / 502 Kalshi problem |
| 6 | insert the run row with status `queued`; the database allows **only one active run per game** | 409 with the existing run's id |
| 7 | start the background task and answer `202` with the run id | |

Use case: stop accidental double clicks and runaway spending, and make the answer instant while the slow work happens later.

### 3.2 Running (`execute_run`)

1. Status becomes `running`, start time recorded.
2. The graph runs with: `thread_id = run id` (saved progress in Postgres), `max_concurrency = MAX_RESEARCHERS`, `recursion_limit = 10`, and LangSmith tags and metadata (run id, event ticker) when tracing is on.
3. When the graph returns, the runner computes **totals**: input and output tokens, searches, and cost from the price table. A model missing from the price table gives **cost unknown** with a note, never zero. A cost above `RUN_COST_WARN_USD` (default 3.00) sets `over_budget` (a flag and a log line; it cannot stop a run already in flight).
4. Status becomes `done` if any findings exist, otherwise `failed` with the reasons.
5. **Sources are saved** (`source_pages`): one row per distinct URL with link, title, time, and the claims that URL was cited for. This is a record of what each source was used for, **not** a copy of the page.
6. Any exception becomes `failed` with a short message. A server shutdown mid-run marks it `failed` ("Interrupted by a server shutdown"). At startup, runs still queued or running are marked `failed` ("Interrupted by a restart"). Runs are not resumed after a restart.

### 3.3 Reading results

- `GET /api/runs/{id}`: the full record (plan, findings, errors, tokens, cost, flags). The result page polls this every 3 seconds only while the run is `queued` or `running`.
- `GET /api/runs`: recent runs (light summaries). `GET /api/runs/latest`: the latest run per game, used by the Games page buttons.

### 3.4 Parallel and sequential, across runs

| Thing | Relationship |
|---|---|
| runs for **different games** | parallel, up to `MAX_CONCURRENT_RUNS` |
| two runs for the **same game** | not allowed at once (database rule) |
| the start-up checks in 3.1 | sequential |
| saving sources and run totals | sequential, after the graph |
| Games page (web app) | the games list and the latest-run lookup are fetched together |

---

## 3b. The games list (Built): where the games a person researches come from

Kalshi offers no "soccer, baseball and tennis games" filter and fetching everything is far too slow (measured on a VPN: thousands of series, events pages of 2 to 5 MB at 8 to 16 s each). So the Games page uses a **configured list of series** (`SPORTS_SERIES`, 15 by default: eight soccer leagues and cups, MLB, Japan's NPB, Korea's KBO, ATP, WTA and both challenger tours). The client chooses the leagues they trade.

```
 GET /api/games  ──► cache fresh (under GAMES_CACHE_SECONDS)? ──yes──► answer from memory (about 10 ms)
                          │ no
                          ▼   one refresh at a time (a lock): simultaneous page loads share it
        for each configured series, up to SPORTS_FETCH_CONCURRENCY at once (parallel):
            GET /events?series_ticker=S&status=open&with_nested_markets=true
        ──► one entry per game, merged, kept in memory
        ──► filter (sport, search text), hide games that already started, sort by start time
```

| Step | Relationship | Notes |
|---|---|---|
| fetching the series | **parallel**, at most 6 at a time | a first refresh of the default list took about 5 s on the VPN; later calls come from memory |
| fetching start times | **parallel** with the series, on its own worker | about 10 s together with the series on the VPN the first time; then cached for 10 minutes |
| two page loads at the same moment | **sequential on purpose** (one lock) | the second waits for the first refresh instead of starting another |
| one league failing | the others still show | the failed leagues are listed on the page; a result with a failure is kept only 10 s so a retry comes soon |
| filtering, hiding, sorting | sequential, in memory | cheap |

What a game entry holds: the event ticker, title ("Coventry vs Newcastle"), detail line, sport, league, start time, and one outcome per Kalshi market with its label ("Newcastle"), the price one can sell at (`bid`) and buy at (`ask`), and the last trade (not shown: it is often zero for markets that do have bids and asks).

**Start times come from Kalshi's milestones, not from the markets.** A market's `occurrence_datetime` is the expected settlement time (about 3 hours after a soccer kickoff, 6 hours after the sampled baseball start), so it is never used. One bulk call for all sports milestones from 48 hours back (about 1,500 of them, three pages) is mapped by every event ticker the milestones list, runs in parallel with the series fetches, and is kept for 10 minutes (a failure is retried after 10 s and the page says start times are unavailable; a game with no milestone shows no start, never a guessed one). When a run starts, one milestones call for that game supplies the kickoff given to the agents.

Games that already started are hidden by default, because Kalshi keeps finished or running games open until they settle and they would sit above the upcoming ones; the page counts them and offers "Show started games".

**Use case:** give the person a short, fast, accurate list of the games the client trades, grouped one row per game. **How it is used:** the page shows it; pressing *Research* starts a run for that game's event ticker (section 3).

---

## 4. Saved progress (checkpoints)

LangGraph writes the graph state to Postgres after each step, under the run id (`thread_id`). **Today** this gives a stored trail and the groundwork for pausing and resuming; **no resume logic is built**. A run interrupted by a restart is marked failed, not continued. The checkpoint tables belong to LangGraph and are created at startup; Alembic is told never to touch them.

---

## 5. Milestone 3: the full prediction (Built on 2026-10-13, not yet run end to end with the real services)

After the research graph (section 2) returns, the runner (`app/research/runner.py`) calls the stages in `app/research/pipeline.py` **one after another in plain code**. They are not more graph nodes: each stage saves its own result in the database, a restarted run is marked failed and not resumed, and the stages do not fan out, so graph checkpoints would add moving parts and no recovery we use. In LangSmith the research graph is one trace and every later OpenAI call (checker, forecasters, baseline) is its own trace. Spec: `docs/specs/FEAT-20261012-1620-milestone-3-prediction.md`.

```
 research graph ─► fetch ─► check ─► forecast ─► compare ─► records ─► done
 (plan, N researchers)                (3 forecasters + plain-AI baseline, at once)
```

| Stage (`runs.stage`) | Kind | What it does | Saved in |
|---|---|---|---|
| `research` | LLM agents with web search | as section 2 | `runs.result`, `source_pages` (link, title, claims) |
| `fetch` | plain code (HTTP) | reads each cited page: public addresses only, checked redirects, size and time limits; every outcome recorded | `source_pages.fetch_*`, `page_text` |
| `check` | LLM judge `gpt-5.4-mini`, one call per page | labels each cited claim supported, not supported or could not check; a verdict stands only with a quote found on the page and the claim's numbers in the quotes | `claim_checks` |
| `forecast` | 3 LLM forecasters `gpt-5.4` + 1 baseline, no search | each sees the game, numbered outcomes and the supported claims only (never a price) and gives a probability per outcome; the baseline sees no facts | `forecasts` |
| median | plain code | median per outcome, spread, min, max; scaled to 100% where exactly one outcome happens | `runs.prediction` |
| `compare` | plain code + Kalshi read | fresh bid and ask, fee from the series, net edge both sides, "meaningful gap" flag with named reasons | `runs.prediction.comparison` |
| records | plain code | one frozen record per outcome for later scoring (`resolve-records`, `score-records`) | `outcome_records` |

Failure rules: research failing fails the run; a later stage failing leaves the run `done` with `prediction.unavailable` naming the stage and the reason; fetching or checking switched off, or no judge or forecaster configured, stops after research and says so; no supported claims continues with evidence `none`; fewer than two valid forecasts gives no prediction and no records.

Design points behind it:
- Forecasters are **not** shown the market price (showing it can make a model echo it); the comparison happens afterwards. Facts reach them in a marked block, one bounded line each, because a sentence on a web page that tells the reader what to answer is also "on the page".
- Page fetching blocks private and local addresses (the URLs come from a model), limits size, time and redirects; about one page in five could not be read in the first sample (bot blocks); Jina Reader was measured and not adopted (notes D30).
- The claim checker is measured against a hand-labelled sample (notes D31): no wrongly supported claim in any run, about 7 of 9 true claims kept.
- Thresholds (`EDGE_MIN`, `MIN_SUPPORTED_CLAIMS`, `MIN_ASK_SIZE`) are placeholders until Milestone 4 has scored real forecasts.

---

## 6. Later steps (Planned, designs only)

**Approval and order** (`NOTEPAD.md` D18). After `compare`: `prepare_order` writes a proposal (market, side, price, quantity, expiry) to the database; `await_approval` pauses the graph with LangGraph's `interrupt()` and does nothing else; when a signed-in person approves or rejects in the web app, the backend resumes the graph with the decision. `place_order` is a **separate** step after approval (because a resumed step runs again from its start, an order in the same step could be sent twice); it rechecks the price, uses the proposal id as Kalshi's duplicate guard, and in paper mode only records a simulated fill. Strictly sequential, one at a time, never in parallel with anything.

**Periodic re-checks** (D15). The same graph run again for a game from a schedule or a new signal, each producing a new forecast row; an updated estimate supersedes any waiting proposal.

---

## 7. Settings that control all of this

| Setting | Default | Controls |
|---|---|---|
| `OPENAI_API_KEY` | none (research is OFF) | whether runs can start |
| `PLANNER_MODEL` | `gpt-5.4-mini` | the lead agent's model |
| `RESEARCHER_MODEL` | `gpt-5.4` | the researchers' model |
| `RESEARCH_REASONING_EFFORT` | `low` | thinking effort of all calls (`low`, `medium`, `high`; never `none`) |
| `MAX_RESEARCHERS` | 4 | most angles, most parallel researchers |
| `MAX_SEARCHES_PER_RESEARCHER` | 3 | web searches per researcher |
| `RESEARCHER_MAX_OUTPUT_TOKENS` | 4000 | output cap per call (planner too) |
| `MAX_CONCURRENT_RUNS` | 2 | runs at once |
| `RUN_COST_WARN_USD` | 3.00 | cost level that flags a run `over_budget` |
| `SPORTS_SERIES` | the default list of 15 series | which Kalshi series appear on the Games page (`Sport:SERIES_TICKER:League label`, comma separated) |
| `GAMES_CACHE_SECONDS` | 60 | how long the games list is kept in memory (10 s when a league failed) |
| `SPORTS_FETCH_CONCURRENCY` | 6 | series fetched at the same time when the list is refreshed |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` | off | traces of every graph run |

Defaults are placeholders until real runs show real costs and times.

---

## 8. Where to change things

| To change | Edit |
|---|---|
| what the planner or researchers are told | `backend/app/research/prompts.py` |
| graph shape, caps, failure handling | `backend/app/research/graph.py` |
| how answers become claims | `backend/app/research/claims.py` |
| model calls and request parameters | `backend/app/research/model.py` |
| prices and cost | `backend/app/research/pricing.py` |
| run lifecycle, totals, saving | `backend/app/research/runner.py` |
| endpoints and run guards | `backend/app/runs.py` |
| the games list and its league list | `backend/app/games.py`, `DEFAULT_SPORTS_SERIES` in `backend/app/config.py` |

## 9. What is proven and what is not (updated 2026-10-12)

**Proven on live services** (four real runs with the real OpenAI key and live Kalshi data, each $0.26 to $0.33 and under a minute): the request settings are accepted (`store=false`, forced search, the search cap, reasoning effort, structured planner output), citation positions line up with the text, the games list and the kickoff times (checked against league and MLB pages), and the instruction changes (plain text, dated odds, no padding or arithmetic). See `docs/discussion/NOTEPAD.md` D27 to D29.

**Not proven:** research quality across many games and leagues (the sample is four games); that "cited" lines are actually supported by their pages (Milestone 3 does that check); behaviour on the client's own network; anything about orders.

