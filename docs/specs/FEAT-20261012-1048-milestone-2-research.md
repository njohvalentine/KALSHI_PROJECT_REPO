# Spec: Milestone 2, research stage (FEAT-20261012-1048 to FEAT-20261012-1054)

Branch: work lands on `master` (base: `master`). No branches are created by Claude.
Design decisions behind this spec: `docs/discussion/NOTEPAD.md` (D3, D4, D7, D12, D15, D21). Milestone definition: `docs/MILESTONES.md`.
Approval: the user approved the task list and, with it, the recommendations on the three open questions (cited pages saved as link, title, quoted text and time; `gpt-5.4-mini` for the planner and `gpt-5.4` for researchers; web app part of this milestone).

## 1. What is being built

Given a Kalshi market, a lead agent plans research angles and several researcher agents run in parallel, each using OpenAI web search on one angle. The result is a list of findings (claims), each tied to the real page links the search tool cited, plus a saved record of every cited page and the cost of the run. A person starts a run from the markets list and reads the result on a prediction page. No probability is produced yet (that is Milestone 3).

## 2. Verified facts this spec relies on

Checked on 2026-10-12 in the installed `openai` 3.29.0 package (not from memory), plus the OpenAI docs pages read earlier (NOTEPAD D7, D12):

- `AsyncResponses.create` accepts `model, input, instructions, tools, tool_choice, include, max_output_tokens, max_tool_calls, reasoning, text, store, metadata`. `AsyncResponses.parse` accepts `text_format` (a Pydantic class) for structured output.
- Web search is the `web_search` tool (`WebSearchToolParam`), with optional `filters.allowed_domains` and `search_context_size` (`low`, `medium`, `high`).
- A response's output contains `web_search_call` items; each has an `action` of type `search` (with `query`/`queries` and `sources`), `open_page` or `find_in_page`.
- Answer text is in `output_text` content parts; each has `annotations`, and a `url_citation` annotation has `url`, `title`, `start_index`, `end_index` (positions in that text).
- `response.usage` has `input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`.
- Prices (OpenAI pricing page, read 2026-10-09, standard tier, per 1M tokens, input / cached input / output): gpt-5.5 5.00 / 0.50 / 30.00; gpt-5.4 2.50 / 0.25 / 15.00; gpt-5.4-mini 0.75 / 0.075 / 4.50; gpt-5.4-nano 0.20 / 0.02 / 1.25. Web search: $10 per 1,000 calls; pages the tool reads are billed as input tokens.
- Per the web search docs: with `tool_choice: auto` the model may skip searching (so we force `required`); `gpt-5.4` with reasoning `none` may give lower-quality search results (so we never set `none`).

**Not verified, because there is no OpenAI key in this environment:** any live call. Everything is tested against mocked responses built from the SDK's own types. Whether `store=false`, `max_tool_calls`, a given `reasoning.effort` value, and the exact character-index convention of annotations behave as documented on the live service is unconfirmed; the first live run must check them (see section 9).

## 3. Module 6 checks

- Lateral spread: the pattern "validated required setting, explicit log line when a feature is off" is applied to the OpenAI key the same way as the existing settings. The run endpoints reuse `require_user` and the `X-Requested-With` guard from sign-in; the route-protection test already covers every route listed in the API schema, so new endpoints are covered automatically.
- Causal depth: the underlying needs are (a) every claim traceable to a real page, (b) bounded cost per run, (c) a run that cannot be started twice by accident, (d) a result that is still there after a restart. Each is addressed below.

## 4. Settings (backend `app/config.py`)

| Setting | Rule |
|---|---|
| `OPENAI_API_KEY` | Optional at startup. If missing, research is **off**: this is logged at startup, and `POST /api/runs` answers 503 "Research is not configured". Never logged, never in traces, never returned by any endpoint. |
| `PLANNER_MODEL` | Default `gpt-5.4-mini` (approved), logged at startup |
| `RESEARCHER_MODEL` | Default `gpt-5.4` (approved), logged at startup |
| `RESEARCH_REASONING_EFFORT` | `low`, `medium` or `high`; default `low` (keeps output tokens, the most expensive part, down) |
| `MAX_RESEARCHERS` | Default 4 |
| `MAX_SEARCHES_PER_RESEARCHER` | Default 3 (sent as `max_tool_calls`) |
| `RESEARCHER_MAX_OUTPUT_TOKENS` | Default 4000 (hard cap per call, includes reasoning tokens) |
| `MAX_CONCURRENT_RUNS` | Default 2 |

Defaults are tuning knobs with safe values (CLAUDE.md Module 4). The numbers are placeholders to be tuned from real run costs.

**Token budget per run:** a hard per-run stop is not possible once researchers run in parallel (they cannot be recalled mid-call). Cost is bounded by the per-call hard caps above (`max_output_tokens`, `max_tool_calls`) and by `MAX_RESEARCHERS`. The run records total tokens and cost, and a run whose estimated cost exceeds `RUN_COST_WARN_USD` (default 3.00) is flagged `over_budget` in its record and logged. This replaces the "maximum tokens per run" idea in the task list.

## 5. Tasks

### FEAT-20261012-1048 OpenAI connection and research settings
- `openai` added to the backend (approved earlier by name).
- Settings above; `research_enabled` is derived from the key being present.
- `app/research/pricing.py`: price table from section 2 and `cost_usd(model, input_tokens, cached_tokens, output_tokens, search_calls)`. A model not in the table gives **no cost** (`None`) and a note, never a silent zero. Cached tokens are billed at the cached rate and removed from the normal input count.
- `app/research/model.py`: a small interface (`plan`, `research`) with one real implementation over `AsyncOpenAI` (wrapped with LangSmith's `wrap_openai` when tracing is on) and a fake one for tests. Calls use `store=False`, `tool_choice="required"`, `max_tool_calls`, `max_output_tokens`, and the web search tool with `search_context_size="medium"`. Returns the text, annotations, search-call count and a usage record.
- Done when: settings tests (missing key logs and disables, bad effort value rejected), cost tests with hand-computed numbers (including cached tokens and an unknown model), and response-parsing tests built from SDK response objects (text with annotations, search-call counting, usage).

### FEAT-20261012-1049 Run records
- Alembic migration adding `runs`: `id` (string uuid), `market_ticker`, `market_title`, `status` (`queued`, `running`, `done`, `failed`), `error`, `created_at`, `started_at`, `finished_at`, `plan` (JSONB), `result` (JSONB), `input_tokens`, `output_tokens`, `search_calls`, `cost_usd` (numeric, null when unknown), `cost_note`, `over_budget` (bool).
- A `created_by` user id so the record shows who started it.
- Done when: migration up/down test; a check constraint on `status`.

### FEAT-20261012-1050 Lead agent (planner)
- A LangGraph node. Input: the market (ticker, title, subtitle, close time, current price, and Kalshi's rules text if present). Output (structured, `parse` with a Pydantic `Plan`): up to `MAX_RESEARCHERS` angles, each with `name` and a specific `question`.
- The planning instructions are written for soccer, baseball and tennis (client's markets, NOTEPAD D21) with a generic fallback: injuries and lineups, recent form, head-to-head, venue/surface, starting pitchers and weather for baseball, and the sportsbook odds consensus as an outside price. The planner must not state any probability.
- More angles than the cap are cut to the cap and the cut is logged and recorded in the run; fewer than one angle fails the run with a clear error.
- Done when: tests with the fake model for the cap, the cut being recorded, an empty plan failing, and the instructions text naming the three sports.

### FEAT-20261012-1051 Researcher agents
- `Send` fan-out from the plan to one researcher per angle, run in parallel with `max_concurrency=MAX_RESEARCHERS`; a reducer merges their results; a later node waits for all of them (verified pattern, NOTEPAD D4).
- A researcher is told to write 3 to 6 findings, one per line starting with `- `, each a specific fact from a page it found, with the date of the information when the page states one, and to say plainly when it finds nothing. It never writes a probability or a recommendation.
- Claims are built from the text lines; a claim's sources are the `url_citation` annotations whose range falls inside its line. A line with no citation is kept but marked `uncited` and not counted as a sourced claim. Source links therefore come only from the search tool's citations, never from URLs the model typed.
- A failing researcher (API error, no usable text) records an error for its angle; the other angles and the run still finish (status `done` with errors listed) unless every researcher failed (then `failed`).
- Run configuration: `thread_id` = run id (saved progress in Postgres), a low `recursion_limit`, LangSmith tags and metadata with the run id and market ticker.
- Done when: tests with the fake model for parallelism (observed concurrency > 1 and never above the cap), claim and citation mapping (including a citation range at a line edge and out-of-range indices), one failing researcher, all failing, and usage totals across nodes.

### FEAT-20261012-1052 Saving cited pages
- After the researchers finish, every cited page is saved to `source_pages` with `run_id`, `url`, `title`, `retrieved_at` (the time of the run), `content` = the quoted text spans cited for that URL (joined, duplicates removed), and `content_hash` of that text. This is **the cited text, not the full page** (approved); full-page saving is added later only if the backtests need it.
- Done when: tests for one row per distinct URL per run, spans merged, hash stable, and nothing saved for uncited lines.

### FEAT-20261012-1053 Run endpoints
- `POST /api/runs` `{ticker}` (login and `X-Requested-With` required): fetches the market from Kalshi (the server's copy, not what the browser sends), refuses with 409 if a run for that ticker is already `queued` or `running`, 429 if `MAX_CONCURRENT_RUNS` runs are active, 503 if research is off; otherwise inserts the run and starts it in the background, answering at once with the run id.
- `GET /api/runs/{id}` returns the record (plan, claims with sources, usage, cost, errors); `GET /api/runs?ticker=&limit=` lists recent runs.
- At startup any run still `queued` or `running` is marked `failed` ("interrupted by a restart"), visibly.
- Background task lifecycle: tasks are kept in a set so they are not garbage collected, are awaited on shutdown with a time limit, and every exception ends in `failed` with a short message (type and text, never a secret).
- Done when: tests with the fake model for the happy path, each refusal, restart cleanup, login required, and a failure ending as `failed`.

### FEAT-20261012-1054 Web app
- Markets list: a button per market. "Analyze" starts a run then goes to its page; "View research" shows when a finished run exists for that market (latest run per ticker).
- `/prediction` lists recent runs; `/prediction/[runId]` shows the market, a status line that updates every few seconds while the run is `queued` or `running` (no auto-refresh once finished), the planned angles, findings grouped by angle with their source links (opening in a new tab) and uncited lines marked, errors per angle, and tokens, searches and cost (shown as "unknown" when the model is not in the price table).
- Same container, tokens and components as Milestone 1. States for: no key configured (503 message), duplicate run (409: link to the existing run), loading, failed, empty.
- Done when: build and lint pass; with a fake backend model in the compose stack the flow works end to end (start, progress, result); content width check repeated on the new pages at 1280px and 390px.

## 6. Order of work and commits

1048, 1049, 1050, 1051, 1052, 1053, 1054. One commit per task; TODO markers `[ ]` to `[o]` to `[x]` with the completion time in the closing commit.

## 7. Dependencies

Backend: `openai` only (already approved). Web app: none beyond Milestone 1.

## 8. Out of scope

Probabilities, forecasters, aggregation, citation verification against the page (Milestone 3), full-page capture, scheduling and periodic re-checks (D15), approval and orders, evaluation, per-run hard cost stop.

## 9. Known limits and first-live-run checklist

- No live OpenAI call was possible while building. First live run (by the user, with the key in `.env`) must confirm: a run completes; every claim line has citations; `store=false`, `max_tool_calls` and the reasoning value are accepted; annotation indices line up with the text; the cost shown matches the OpenAI usage page within a few percent; one run's real cost and time (this tunes the default caps).
- Quality of the research (are the angles useful, are the facts right) can only be judged on real runs; nothing in this milestone measures it. Milestone 4 does.
- Sportsbook odds appear only if the search finds a page showing them; no odds provider is integrated.

## 10. Deviations recorded during the build (2026-10-12)

- **What "saving cited pages" can hold (FEAT-20261012-1052):** the approved wording was link, title, quoted text and time. OpenAI's `url_citation` annotation carries only the link, the title and where the citation sits in the answer text; it carries no text from the page, and the range it marks is the inline link markup, not a quotation. So each saved row holds the link, the title, the time, and the claims (our own words) the page was cited for, in the `content` column. It is a record of what each source was used for, not a snapshot of the page. A true page snapshot needs our own page fetch; the decision to add it waits for the first backtests (spec section 5, task 1052, and section 8).
- **Token budget:** as written in section 4, the hard limits are per-call caps and the researcher count, plus a recorded `over_budget` flag; there is no per-run hard stop.
- **Alembic and LangGraph tables:** `alembic revision --autogenerate` proposed dropping LangGraph's checkpoint tables because they are not in the models. `alembic/env.py` now ignores them, and a test (`alembic check` with the tables present) guards it.
- **Web app wording (FEAT-20261012-1054):** the spec's mockup used "Source checked". Nothing checks sources against pages yet (Milestone 3), so the result page says "Cited" (the search tool attached a link) and "No source given", with a note saying sources are not yet checked and no probability exists yet.
- **"Analyze again":** a market with a finished run keeps an "Analyze again" button next to "View research", so a market can be re-run; the one-active-run rule still applies. Each press costs money, which the button does not warn about yet.
- **How the end-to-end check was done without an OpenAI key:** the OpenAI SDK was pointed at a small mock server (`OPENAI_BASE_URL`) returning the same response shapes, so the real `OpenAIResearchModel`, the SDK's parsing and the database path were exercised over HTTP. The mock's content is canned (every angle returns the same lines); it proves the plumbing, not research quality. The mock servers and the mock data were removed afterwards.
- **Database rule:** a partial unique index (one active run per market) was added in its own migration (`d178265cbd60`), not only an application check.
