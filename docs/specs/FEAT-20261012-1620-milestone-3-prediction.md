# Spec: Milestone 3, full prediction per game (FEAT-20261012-1620 to 1629)

Branch: `feature/sports-games-list` (base `master`, not merged). The user approved the plan on 2026-10-12: check claims before forecasting; fetch the pages ourselves; hide the market price from the forecasters; median; three forecasters (a setting); Jina Reader as a fallback for JavaScript pages, after a measured comparison. Why each was chosen and what was rejected: `docs/discussion/NOTEPAD.md` (D23, D26) and `docs/agent/GRAPHS.md`.

**How this spec is used.** Tasks 1 and 2 are fully specified below and need approval before code. Tasks 3 to 10 have their decisions fixed here and get a detailed section added (and approved) when each one starts, so a finding from an earlier task can change a later design.

## Verified starting point (code read 2026-10-12)

- `source_pages` (`app/models.py`) holds, per cited link, `content` = the claims it was cited for, joined. That is **not** page text (see the note in `app/research/sources.py`). `content_hash` hashes that same text.
- Claims live inside `runs.result` (JSON `findings` → `claims` → `sources`); they have no ID of their own.
- `runs.status` goes queued → running → done/failed; there is no stage inside "running".
- The `forecasts` table (one yes/no price per market) is **used by no application code**, only by `tests/test_migrations.py`. Its shape (one market, one "yes" Kalshi price recorded next to the forecast) is the opposite of what we decided (per game, one probability per outcome, forecasters never see the price).
- `uv` has `httpx2` for HTTP; no HTML parser package is installed. Python's `html.parser` is built in.

## Task 1: data shape (FEAT-20261012-1620)

One Alembic migration (generated with `alembic revision --autogenerate`, reviewed):

1. `source_pages`: keep the existing columns (they remain the record of what each link was cited for) and add:
   - `fetch_status` text, not null, default `not_fetched`; allowed: `not_fetched`, `ok`, `blocked` (address or scheme not allowed), `empty_js` (page needs JavaScript or has almost no text), `unsupported` (type we cannot read, e.g. PDF before the Jina task), `too_large`, `failed` (network, HTTP error, timeout). Check constraint.
   - `fetch_method` text null (`plain` or `jina`), `final_url` text null, `http_status` int null, `fetched_at` timestamptz null, `fetch_detail` text null (short reason shown to the user), `page_text` text null, `page_text_hash` varchar(64) null.
2. New `claim_checks`: `id`, `run_id` (indexed), `finding_index` int, `claim_index` int, `source_url` text, `verdict` text (`supported` / `not_supported` / `could_not_check`, check constraint), `reason` text, `model` text, `created_at`. Unique on (`run_id`, `finding_index`, `claim_index`, `source_url`). A claim cited to several pages gets one row per page; the claim goes forward if **any** page supports it (decided now so the checker and forecasters agree).
3. Replace `forecasts` with a new per-game table, same name, in the same migration (drop and create; no data in it, verified by the `ix`/code search above and a row count in the migration test):
   - `id`, `run_id` (indexed), `market_ticker` (one row per outcome of the game), `forecaster_index` int (0-based; `-1` is not used), `variant` text (framing used), `probability` numeric(5,4) with a 0..1 check, `reasoning` text, `model` text, `created_at`.
   - Resolution is **not** stored here. It is filled in Milestone 4 into its own table when scoring exists (no empty columns waiting for later).
4. `runs`: add `stage` text null (`research`, `fetch`, `check`, `forecast`, `compare`, `done`; the page shows it while running) and `prediction` JSONB null (per outcome: median, spread, min, max, counts of supported claims, and the market comparison from task 7). The existing `result` JSON is unchanged.

Models in `app/models.py` are the source for the migration. `tests/test_migrations.py` is updated: the table list and the old per-market forecast checks are replaced by checks for the new constraints (verdict values, probability range, fetch status values, unique claim check).

**Tests:** migration up and down on a fresh database; each check constraint rejects a bad value; unique claim check; the old tests that still apply keep passing.

**Not in this task:** any use of the new columns.

## Task 2: safe page fetcher (FEAT-20261012-1621)

New module `app/research/fetch.py`. Input: the run's cited URLs. Output: updates the matching `source_pages` rows (status, text, times). Called from the run after the researchers finish (wiring into the graph is task 10; this task ships the fetcher and its tests, plus a function that can be called on a finished run).

**Rules, in the order they are applied (each failure sets `fetch_status` and a short `fetch_detail`, never silently skips):**
1. Scheme must be `http` or `https`; port must be 80 or 443; no username or password in the URL; otherwise `blocked`.
2. Resolve the host name ourselves. **Every** address returned must be public: `ipaddress` flags `is_private`, `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`, `is_unspecified`, and the cloud metadata address range are refused (also IPv4-mapped IPv6 forms and numeric hosts like `2130706433`). If any address is not public, the URL is `blocked`.
3. Connect to the **address we checked**, not to the name again (this closes the gap where a name answers "public" to our check and "private" to the connection). The request keeps the original `Host` header and TLS name. How to do this with `httpx2` (custom transport or a pinned address) must be checked against the installed version's documentation before building (CLAUDE.md Module 3); if it cannot be done cleanly, the task stops and comes back to you with options.
4. Redirects are followed by us, at most 4, and **every hop goes through rules 1 to 3 again**.
5. Time: 10 seconds connect-and-read per request, 25 seconds total per page. Size: stop reading after 2 MB. Accept only `text/html`, `application/xhtml+xml` and `text/plain`; other types are `unsupported` (PDF is picked up by task 3 of this list, the Jina fallback). Compressed responses are decoded with a size limit on the **decoded** bytes (no decompression bombs).
6. Text extraction with Python's built-in `html.parser`: drop `script`, `style`, `noscript`, `template`, `svg`, `head` content except `<title>`; keep text; collapse whitespace; cap stored text at 200,000 characters. If the result has fewer than 200 characters, or contains an "enable JavaScript" style message and little else, the status is `empty_js`.
7. Save `page_text`, its hash, `fetched_at`, `final_url`, `http_status`, `fetch_method = plain`.

**Settings (behavior knobs with safe defaults, added to `.env.example`, validated at startup):** `FETCH_ENABLED` (true), `FETCH_MAX_PAGES_PER_RUN` (25; more distinct links than this are left `not_fetched` with a log line and a visible note), `FETCH_CONCURRENCY` (5), `FETCH_TIMEOUT_SECONDS` (10), `FETCH_MAX_BYTES` (2,000,000). No required config, so nothing fails at boot; a bad value does.

**Identity:** a fixed `User-Agent` naming the tool. We do not read or follow `robots.txt` (flag for you: some sites' terms forbid automated reading; the pages are those the web search already returned; we send one request per page and do not crawl).

**Lateral check:** the app makes outbound requests in two other places, the Kalshi client (fixed base URL from settings) and OpenAI (SDK). Neither takes a URL from untrusted text, so the address rules apply to the fetcher only.

**Tests (written first):** private, loopback, link-local, metadata, IPv6, IPv4-mapped and numeric-host URLs are refused; a public name that resolves to a private address is refused; a name with one public and one private answer is refused; a redirect to a private address is refused at the hop; more than 4 redirects; wrong scheme and port; size limit and decoded-size limit; wrong content type; timeout; extraction drops scripts and styles and keeps the title; empty page and JavaScript-message page give `empty_js`; page limit per run. Tests use a local fake server and a fake resolver, so they make no real network calls.

## Decisions already fixed for tasks 3 to 10 (detail comes before each build)

- **Jina (1622):** official image `ghcr.io/jina-ai/reader:oss` (Apache-2.0, stateless mode, headless Chrome). Own container on its own Docker network with no route to the database or backend networks, CPU and memory limits, no published port. We still check every URL and redirect with the rules above before Jina sees it. It is used only for `empty_js` and PDF pages. Before it is wired in: run it locally on the saved sources of the four real runs, compare plain and Jina (empty count, time), and report the numbers. Its safety against private addresses is unverified by Jina's docs, so it is also tested with private-address URLs.
- **Checker (1623, 1624):** judge `gpt-5.4-mini`; sees the claim and the saved page text only; labels `supported` / `not_supported` / `could_not_check`; pages without text are `could_not_check` (visible, not dropped). Accuracy measured on about 20 hand-labelled claims before it is trusted.
- **Forecasters (1625):** `gpt-5.4`, no web search, three runs with different framing, count in a setting; the prompt contains the game, outcomes, rules, start time and the supported claims only; never a price.
- **Aggregate (1626):** median per outcome; the spread (max minus min) is stored. Outcomes of a game are normalized to sum to 1 only if Kalshi's outcomes are mutually exclusive and exhaustive (to be checked per game type in that task's section).
- **Comparer (1627):** uses the price a bet can be placed at (ask for yes, 1 minus the bid for no) and the fee estimate; "meaningful gap" needs gap above a placeholder threshold, spread below a limit, and enough supported claims. Thresholds are settings and are placeholders until Milestone 4.
- **Cost (1628):** new model calls go into the existing usage totals and the warning level.

## Risks

- A cited page can be stale or a derived claim cited to a page that does not say it: the checker is the answer, and its accuracy is measured, not assumed.
- Fetching raises the safety surface; the tests above are the main defense, and the Jina task adds a browser.
- Extra cost per game is not measured yet; it is measured on the first full run.

## Task 2 result, and detail for the Jina task (FEAT-20261012-1622)

**Plain fetcher measured on the 46 distinct pages cited in the four real runs (2026-10-12, through the user's VPN, 2 to 11 s per page):**

| Result | Pages | Notes |
|---|---|---|
| ok | 37 | text saved; sizes from 0.9k to 11k characters |
| failed, HTTP 403 | 8 | atptour.com, betmgm.com, oddschecker.com (2), reutersconnect.com, rotascore.com, worldfootball.net, it.wikipedia.org (bot blocking) |
| failed, no DNS | 1 | img.legaseriea.it (an image host) |
| empty_js | 0 | |

Two things the numbers do not show and the Jina comparison must: (1) several "ok" pages are short (about 900 to 1,500 characters, mostly on legaseriea.it and veneziafc.it) and may be navigation text from a page whose real content loads with JavaScript, so "ok" is not "has the content"; (2) the 403 pages are the odds and tennis sources, the ones most useful for the forecast. The list of non-ok links is kept so the same pages can be tried with Jina.

**Jina Reader facts (official README, read 2026-10-12):** image `ghcr.io/jina-ai/reader:oss`; `docker run --rm -p 3000:8081 ...`; no required settings; stateless by default; call is `GET http://host:port/<full URL>` with `X-Respond-With: text` (or `markdown`), `X-Timeout` (max 180) and `Accept: application/json` for JSON; any `.pdf` is parsed with PDF.js; `x-proxy-url` lets a request go through our own proxy. The README states no memory or CPU need and **no option to block private or internal addresses**.

**The safety problem (decision for you):** our own checks stop a bad link before Jina sees it, but not what Jina's Chrome does afterwards (a JavaScript redirect, a page that loads an internal address). A container in the default network can reach the host and the local network. Options:

1. **Egress proxy (recommended if Jina proves worth it):** the Jina container is reachable only from the backend, has no other route out, and sends all its web traffic through a small filtering proxy container that refuses private addresses (Jina's `x-proxy-url` header). One more small container; the rule is enforced where the traffic leaves, so Chrome cannot go around it. A proxy package (for example Squid or tinyproxy) is a new dependency to approve then.
2. **Host firewall rules** on the machine that runs Docker (block private ranges from the Jina network). Works, but lives outside the repo and is easy to forget at handover.
3. **No extra protection** (only our URL checks). Rejected: it leaves the Chrome gap open.

**Plan, in order:**
1. Measurement only (no code in the app): run the image locally, send the non-ok links and ten of the short "ok" links, compare text length and content with the plain fetch, and record the time. Result goes in this file. If Jina recovers few pages or is slow, stop here and keep the plain fetcher.
2. Only if worth it: the container, the proxy (option 1), the app fallback (`empty_js`, `unsupported` PDF and optionally 403 go to Jina, `fetch_method = jina`), tests including private-address URLs sent through the proxy, and the compose wiring.

## Jina measurement and outcome (2026-10-12)

Measured as planned: the official image, run locally with 2 CPUs and 3 GB, called on the 23 pages that were not ok or were short in the plain fetch. Results and the decision are in `docs/discussion/NOTEPAD.md` D30. In short: one of nine failed pages recovered, four bot walls returned as HTTP 200 with fake "content", 10 to 49 s per page, and a 3.3 GB image that needs an egress proxy to be safe. **Not adopted.** FEAT-20261012-1622 is closed as measured, not built; the "Plan, in order" step 2 above is dropped. The checker (task 3) must handle menu-only pages and bot-wall text as "could not check".

## Task 3 detail: claim checker (FEAT-20261012-1623), for approval

Branch `feature/sports-games-list`. New module `app/research/check.py`. This task delivers the checker and its tests; calling it from a run is task 10 (`FEAT-20261012-1628`), as with the fetcher.

**What is checked.** Every claim of kind `sourced` (it has at least one cited link), once per cited link. Claims of kind `uncited` and `none` are not checked and **never go forward** (what the user approved: only supported claims go forward; the rest stay visible).

**Verdict rules (the important part).** Three verdicts, and the default is the safe one:
- `supported`: the page text says what the claim says, including every number, name, date and team. The judge must give a **short quote copied from the page**. We then check the quote really appears in the saved page text (after collapsing whitespace and case); if it does not, the verdict is **changed to `could_not_check`** with the reason "quote not found in the page". This is the guard against a model inventing support, and against a page that tells the model what to answer.
- `not_supported`: only when the page text **contradicts** the claim or states a different value for the same thing (a quote is required here too, same verification). A page that merely does not mention the claim is **not** this verdict.
- `could_not_check`: everything else: page not readable, page is only menus or a bot wall, claim not found, claim is derived by calculation (for example "rest days") and the page does not state it, or the page has no usable date for a time-sensitive claim such as odds.
So an unreadable or menu-only page can never turn a claim into "not supported".

**Cases that need no model call (decided in code, recorded with a reason):** the page's `fetch_status` is not `ok` (reason is the saved `fetch_detail`); the page text is shorter than 200 characters after cleaning; a bot-wall text ("verifying you are human", "security verification", "access denied" and similar short pages) is also caught by the length rule in practice, and the judge is told about it as well.

**How it calls the model (one call per page, not per claim).** A page cited for several claims is sent once with all of them numbered, so the cost grows with pages, not claims.
- Model: `gpt-5.4-mini` (setting `CHECKER_MODEL`), no tools, `store=false`, reasoning effort from the existing setting, structured output (`responses.parse`, the same call style the planner already uses and which was confirmed live): a list of `{claim_number, verdict, quote, reason}`.
- Page text sent: the first `CHECK_PAGE_CHARS` characters (default 30,000, about 7,500 tokens). If the page is longer, the judge is told the text was cut, and a missing fact in a cut page is `could_not_check` (never `not_supported`). Ceiling: facts after the cut are missed; raise the setting if the real runs show it matters.
- The page text is untrusted. It goes inside a clearly marked block, the instructions say that anything inside it is data and not instructions, and the quote verification above limits what an injected sentence can achieve. The model has no tools, so there is nothing for an injection to call.
- The claim text, the game, the page's URL and title and today's date are sent; **no prices**.
- Output size capped (`CHECKER_MAX_OUTPUT_TOKENS`, default 1500). A reply that is not valid for the schema, or misses a claim number, marks the missing claims `could_not_check` with "judge gave no answer for this claim" and is logged; it never raises through the run.
- At most `CHECK_CONCURRENCY` (default 5) pages are judged at once.

**What is saved.** One `claim_checks` row per claim and page (`verdict`, `reason` including the verified quote, `model`). Usage of each call is returned in the same shape as the researchers' usage so the run total includes it. Saving is idempotent: the unique constraint means re-checking a run replaces nothing silently (a repeat is skipped and logged).

**The rule that decides what goes forward** is one small function, `supported_claims(findings, checks)`: a claim goes forward if **any** of its pages has `supported`; `not_supported` on one page does not cancel `supported` on another, but is kept visible. The forecasters (task 5) receive only what this returns.

**New settings (tuning knobs with defaults, in `.env.example` and compose):** `CHECK_ENABLED` (true), `CHECKER_MODEL` (`gpt-5.4-mini`), `CHECK_PAGE_CHARS` (30000), `CHECKER_MAX_OUTPUT_TOKENS` (1500), `CHECK_CONCURRENCY` (5). With `OPENAI_API_KEY` unset, checking is off exactly as research is: the run refuses to start (already the case), no silent change.

**Expected cost (unmeasured):** about 25 pages × 8k tokens of input is roughly 200k tokens, about 15 cents at the mini price, plus a little output. The real number comes from the sample in task 4.

**Lateral check:** the researcher and planner calls build their requests in `OpenAIResearchModel`; the checker gets its own small class beside it with the same client, tracing wrapper and error type, so there is one place that makes OpenAI calls of each kind and the same failure handling. The same "model output must be verified against the source it points to" idea applies to the forecasters' reasoning later; it is not needed there because they cite nothing.

**Tests (fake model, no network):** unreadable page, short page and bot-wall page give `could_not_check` with no model call; a supported verdict with a quote that is on the page stays supported; the same verdict with a quote that is not on the page becomes `could_not_check`; `not_supported` needs a verified quote and is otherwise downgraded; a missing claim number and an invalid reply both give `could_not_check` for the missing claims; one call per page with its claims numbered, and several pages run with the concurrency limit; cut pages are labelled to the judge; `supported_claims` takes any page's support and ignores uncited claims; usage is returned; re-checking a run adds no duplicates; the prompt contains no price and the page is inside the marked block.

**Task 4 (separate detail before it starts):** the hand-labelled sample and a script that scores the checker against it. The labels will be written by me from the saved pages and must be spot-checked by you, because I cannot be an independent judge of my own pipeline's labels; that limit is part of the result.
