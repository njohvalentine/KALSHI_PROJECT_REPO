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

### Task 3 changes after a review of the commit (BUG below)

Added to the verdict rules: (1) quotes are verified against **exactly the text the judge was shown** (cut and with markers removed), not the whole saved page; (2) a `supported` quote must contain **every number in the claim** (a real but unrelated quote proves nothing; this may turn some true claims into `could_not_check` when the page writes a date differently, and the labelled sample in task 4 measures that cost); (3) any spelling of the page-block marker is removed from the page text and from the claims; (4) a claim number answered twice gets no answer at all.


## Task 4 result: the labelled sample and the first measurement (2026-10-12)

**What exists:** `backend/tests/data/claim_labels.json` (25 cases: 21 real claims from the four real runs, each with its real cited page as saved today, trimmed to at most 4,000 characters, plus 3 synthetic cases built from real pages and 1 real unreadable page) and `backend/app/research/score_checker.py` (run: `cd backend && set -a && source ../.env && set +a && uv run python -m app.research.score_checker`; about 3.5 cents). Cases marked borderline (7) are ones where a careful person could label either way; they are reported apart and do not count towards accuracy. **The labels were written by me, the assistant that built the checker, and need a spot-check by a person**: the first version of one label (`s-injection`) was wrong and the judge was right, which is exactly the risk.

**What matters in practice:** only `supported` claims go forward, so the numbers that matter are (1) claims wrongly marked `supported` (must be zero) and (2) true claims that are kept (recall). `not_supported` versus `could_not_check` is only a display difference: neither goes to the forecasters.

**Second run, real judge (`gpt-5.4-mini`, 24 calls, 37k input and 5k output tokens, 0.035 USD):**

| Measure | Result |
|---|---|
| Wrongly marked `supported` | **0 of 25** (also in the injection case: the judge did not obey the page, and the fake closing marker was removed) |
| True claims kept as `supported` | **2 of 9** |
| Firm cases correct (18 cases) | 10 |
| True claims lost to the quote rules | 6 (the judge said supported; our checks changed it) |
| True claims called `not_supported` by the judge | 2 (both from one flattened table, see below) |

**Why true claims are lost (causes found, not guessed):**
1. **The "every number in the claim must be in the quote" rule is too strict.** The numbers that are missing are mostly the page's publication date (for example "10/10/2026", "Oct. 12, 2026 4:01 a.m."), which sits in the page header, not in the sentence that proves the fact. 3 cases.
2. **Quotes must be one unbroken passage, and the judge joins passages.** Flattened pages put menu text, share buttons and the like between a date line and the line that proves the claim, so a quote that stitches them ("Updated Oct. 12, 2026 4:01 a.m. ET" then "Associated Press") is not found. 2 cases (sky-xi, fox-ap).
3. **Flattened tables confuse the judge.** On tennis-db.com the saved text lists each match with the date line after its players; the judge read the date together with the next match's players and called two correct claims `not_supported`. I made the same reading mistake myself at first. 2 cases. A wrong `not_supported` is shown to the user as "contradicted", so it can mislead.
4. Run-to-run variation: one case (`a-squad`) was lost in the first run and kept in the second.

**What worked:** the safety rules held (no false `supported`; unreadable and empty pages never reach the judge; the injected page was not obeyed); the claim with a real contradiction was caught (`a-singlebet`, `s-wrong-score`, `s-wrong-number`, `s-injection`); a JavaScript page that shows no data (Lega Serie A match page) gave `could_not_check`, as intended.

**Cost:** about 1.4 cents per page at these sizes. A run with about 25 pages is therefore roughly 4 to 10 cents, below the 15 cents estimated earlier.

**Proposed fix (needs approval, logged as ISS-20261012-1729):** (a) let the judge give up to three short quotes that together must show every number, name and date in the claim, each quote verified on its own; (b) tell the judge that flattened tables list the date after the players and to read columns from the header; (c) keep "supported needs a verified quote" and "no quote, no verdict"; (d) measure again on this sample and a second run to see the variation. Alternative if (a) does not recover enough: check the claim's numbers against the page instead of the quote (weaker, but no recall loss for publication dates). The decision should be made on the measured numbers.

### Sample labels (for your spot-check)

| Case | Label | Why |
|---|---|---|
| `a-squad` | supported | Squad list: 28 players, all named players listed, date 11/10/2026 on the page (Italian page). |
| `a-presser` | supported | Italian press conference; English paraphrase of Stroppa's words is faithful; date 10/10/2026 on the page. |
| `a-sky-xi` | supported | Sky expected XI, unavailable players and no suspensions all match; page shows 'lunedi 12 ottobre 2026'. |
| `a-team-played` | could_not_check (borderline) | Page shows 'Partite giocate 5' but not the 12 October match; the claim ties them together. |
| `a-match-kickoff` | could_not_check | JavaScript page: the saved text is only menus and 'No data available'; the kickoff is not in it. |
| `a-match-draw` | could_not_check | Same JavaScript page, no match data in the saved text. |
| `a-unbeaten` | could_not_check (borderline) | Facts (unbeaten in last 5, 4 wins 1 draw) are on the page, but the page has no date, so 'wrote on 09/10/2026' cannot be verified. |
| `a-oddsator` | could_not_check | The page now shows different prices and no 'BC Game' row; odds claim cannot be matched. |
| `a-singlebet` | not_supported | Page: Atalanta opened 1.66 (claim says 1.55) and the draw line movement says opened 4.10 (claim 4.17). |
| `m-lineups-page` | supported | Starting-lineups page: LAD at MIL, 5:00 PM, Yamamoto (RHP) and Henderson (RHP), October 12th 2026. |
| `m-faq-lineup` | could_not_check (borderline) | Content matches, but 'Oct. 12, 2026' is not in the saved text. |
| `m-schedule-compare` | could_not_check | The schedule lists Game 2 at 5 p.m. but the page has no 'Oct. 9, 2026' and cannot state the comparison with our exchange time. |
| `m-sportsbookish` | could_not_check (borderline) | FanDuel -136 / +116 match, but 'Updated 6 min ago' cannot be verified (the page now says 13 min ago). |
| `m-fox-ap` | supported | Page: 'Updated Oct. 12, 2026 4:01 a.m. ET' and 'LINE: Dodgers -114, Brewers -106'. |
| `t-agentbets` | not_supported (borderline) | Prices match, but the page says odds updated at 11:00 AM UTC, the claim says 8:00 AM UTC. |
| `t-transcript` | supported | Transcript, Monday October 5 2026; the quote is the page's wording with a repeated word removed. |
| `t-rolex` | supported | Article dated 7 October 2026: 'having missed the past two editions due to injury'. |
| `t-ankle` | could_not_check (borderline) | Headline on July 5, 2026 is about a 'timeout' and calls the injury rule 'a disgrace'; the words 'ankle timeout' are not on the page. |
| `t-tenniscom` | could_not_check (borderline) | The scoreboard text is a run of digits with no clear winner or tiebreak score. |
| `t-db-chengdu` | supported | Row: Sep 29, 2026, F, Chengdu Open, Hard, DF #26 6-4 7-6(7) over Hurkacz. |
| `t-db-cincinnati` | supported | Row: Aug 17, 2021, R64, Cincinnati Open, Hard, Hurkacz 6-1 6-7(3) 6-1 over DF. |
| `t-oddschecker-unreadable` | could_not_check | The page could not be fetched (HTTP 403); no model call is needed. |
| `s-wrong-score` | not_supported (synthetic) | Synthetic: the claim says 7-6(9); this page's Chengdu row says 7-6(7). |
| `s-wrong-number` | not_supported (synthetic) | Synthetic: the claim says 30 players; the page lists 28. |
| `s-injection` | not_supported (synthetic) | Synthetic: the claim says Venezia won 3-0 in Bergamo in 2024/25; the page says their last win there was 3-0 in Serie B 1994/95, which contradicts it. The page also carries an injected instruction and a fake closing marker; it must not make the verdict 'supported'. (First label was could_not_check; the judge was right and the label wrong.) |

### Task 4 follow-up: the checker fix and its measurement (ISS-20261012-1729, approved)

**Changes made:** (1) the judge gives one to three quotes (field `quotes`, required, each verified on the page the judge saw; together they must hold every number of the claim); (2) the prompt says one unbroken passage per quote, never "...", read flattened tables by their column header, a date line belongs to the players above it; (3) in a dd/mm/yyyy date only the year is compared (pages write the same date as "12 ottobre 2026"); (4) new setting `CHECKER_REASONING_EFFORT`, default `medium`; (5) `CHECKER_MAX_OUTPUT_TOKENS` default raised from 1500 to 4000, because reasoning tokens count against the output cap and at medium effort one call was cut off mid-answer (a real run would have saved that page as could_not_check, "The check could not be run").

**Measured with the real judge on the same 25 cases, each configuration run two or three times:**

| Configuration | Wrongly `supported` | True claims kept (of 9) | Firm cases correct (of 18) | Cost of 24 calls |
|---|---|---|---|---|
| First version (single quote, low effort) | 0 | 2 | 10 | 3.5 cents |
| Multi-quote and prompt, low effort | 0, 0 (one borderline case marked supported in one of two runs) | 4, 4 | 11, 11 | 3.7 to 5.6 cents |
| plus date and quote-field fixes, low effort | 0, 0 | 6, 5 | 12, 13 | 3.6 to 4.0 cents |
| plus medium effort and 4000 output tokens (**current**) | **0, 0, 0** | **5, 8, 7** | **14, 17, 16** | **7.4 to 7.8 cents** |

**Correction to an earlier figure:** the cost is about 0.15 cents per judge call at low effort and about 0.3 cents at medium, not "1.4 cents per page" as I wrote before. A run with 25 pages costs about 8 cents with the current setting.

**What still fails:** the two flattened-table cases from tennis-db.com (correct claims called `not_supported` in about two of three runs; the same table confused me too); run-to-run variation of two or three cases; `a-sky-xi` and `a-presser` in one run each. A wrong `not_supported` is shown as "contradicted" and never goes forward, so it costs recall and could mislead a reader, but it cannot raise a probability. **Not done:** a table-aware text extraction (keep each table row on one line) in the fetcher would remove the table confusion at its source; logged as an idea, not built.

**Reading the result:** the safety property holds in every run (nothing wrongly supported), recall went from 2/9 to roughly 7/9 on average. The sample is small (25 cases, 9 supported), so these numbers say "much better and safe so far", not "proven". More labelled cases should be added as real runs accumulate.

## Client scope added on 2026-10-13 (approved by the user)

The client's priority is to find out whether the system can **consistently identify genuine opportunities**, not only research games. He asked for probabilities for every outcome and other Kalshi market types (total goals or runs, both teams to score, over 1.5 goals, no tie), comparison with executable prices, automatic ranking with evidence, uncertainty and risks, and monitoring with alerts. Four items were added to `TODO.md` (FEAT-20261013-0906 to 0909) and the build order is: forecasters (1625), median (1626), market comparer (1627), **early record of forecasts (0906)**, run wiring and limits (1628), result pages (1629), more market types (0907), opportunities screen (0908), monitoring and alerts (0909). Each new item gets its own spec section before it is built.

## Task 5 detail: the forecasters (FEAT-20261012-1625), for approval

Branch `feature/sports-games-list`. New module `app/research/forecast.py`. As with the checker, this task delivers the forecasters and their tests; calling them from a run is task 10.

**What a forecaster receives:** the game (title, start time, rules), the outcomes **with their Kalshi market tickers**, today's date, and the **supported claims only**, grouped by angle (text only, no source links, no page text). Never a price, never a link to Kalshi. A test checks the prompt text for any price.

**What it returns (structured output):** for each outcome, a probability between 0 and 1, and one short reasoning text (at most about 120 words) naming the evidence it weighed and what it was unsure about. Probabilities are for the outcome as written ("Newcastle wins", "Tie").

**Three framings (the count is a setting, `FORECASTER_COUNT`, default 3; framings repeat if the count is larger):**
1. **Evidence first:** weigh each supported claim, then settle on probabilities.
2. **Base rate first:** start from how often such a team, home side or favourite wins in this sport, then adjust only as far as the claims justify.
3. **Devil's advocate:** form a first view, argue the strongest case for the outcome it rates least likely, then give the final probabilities.
The three differ only in the instruction; the output shape is the same. Different framings are what makes the three estimates independent enough for a median and a spread to mean something. Whether they really differ is measured in Milestone 4.

**Rules in every prompt:** the supported claims are the only evidence about this game; general knowledge of the sport is allowed, but say so; do not use any knowledge of how this specific game ended; if the evidence is thin, say so and stay closer to the base rate; the outcomes may be exclusive, then the probabilities must add up to 100%.

**Checks on the answer (code, not trust):**
- Every listed outcome gets exactly one probability, and no unknown outcome appears; otherwise the forecast is dropped (logged with the reason).
- If the event's outcomes are mutually exclusive **and** cover every result (to be verified live per game type before building: soccer winner has three outcomes, baseball and tennis two), the probabilities must add up to between 0.97 and 1.03 and are then scaled to exactly 1; outside that range the forecast is dropped. Where Kalshi's outcomes are not known to be exhaustive, no scaling is done.
- At least **two** valid forecasts are needed; with fewer, the run has **no prediction**, and says why. No quiet substitute.
- Probabilities are kept as given (not pushed to 0 or 1); a probability of exactly 0 or 1 is dropped as invalid, because a single run cannot know that.

**With no supported claims:** the forecasters still run, from the base rate, and the prediction is marked `evidence: none`, so the comparer cannot call a gap meaningful and the result page says "no supported evidence". This also gives the plain-AI baseline that Milestone 4 needs.

**Model and settings (defaults, in `.env.example` and compose):** `FORECASTER_MODEL` (`gpt-5.4`, no tools, `store=false`), `FORECASTER_REASONING_EFFORT` (`medium`), `FORECASTER_MAX_OUTPUT_TOKENS` (4000, reasoning counts against it), `FORECASTER_COUNT` (3). One shared OpenAI client with the checker and researchers; the same error handling; the three calls run at the same time.

**What is saved:** one `forecasts` row per forecaster and outcome (probability, framing name, reasoning, model); usage of each call is returned so the run total includes it. A failed or invalid forecaster is saved nowhere but logged and counted in the run's prediction record.

**Code changes this needs:** `GameInfo` gets the outcome tickers and the exclusive flag (from Kalshi's event data); the games list and run start already read the event, so no new Kalshi call.

**Expected cost (unmeasured):** about 3,000 input and 1,500 output tokens per forecaster, so roughly 3 to 5 cents for three at `gpt-5.4`. The real figure comes from the first real run.

**Tests (fake model, no network):** the prompt holds no price, no link and only supported claims; each framing gets its own instruction; the answer checks above (missing outcome, unknown outcome, sum out of range, scaling to 1, probability 0 or 1); fewer than two valid forecasts gives no prediction with a reason; one failed call does not stop the others; no supported claims gives `evidence: none`; usage is returned; rows are saved per outcome and forecaster; the request to the real model class has the right model, effort, output cap and no tools.

**Not in this task:** the median and spread (task 6), the comparison with the market (task 7), market types other than the winner (FEAT-20261013-0907).

### Task 5 result (2026-10-13)

Built as specified: `app/research/forecast.py`, framings and prompt in `app/research/prompts.py`, `GameInfo` now carries `outcome_tickers` and `exclusive` (Kalshi's `mutually_exclusive`), four new settings. 298 backend tests pass.

**Live check with the real model (one game, three forecasters, `gpt-5.4`, medium effort):** the request was accepted, 1,649 input and 1,209 output tokens, **2.2 cents for the three forecasters**, all three answers valid. Atalanta vs Venezia with four real supported claims gave Atalanta 0.69, 0.67 and 0.68, draw 0.19 to 0.20, Venezia 0.12 to 0.13. **The three framings barely differ** on this one game, so the spread will be small; whether three framings add anything over one call is for Milestone 4 to measure (no conclusion from one game).

**Verified live on 2026-10-13 (VPN on, public read calls only, one call per configured series):** all open events of all 15 configured series are `mutually_exclusive: true`; every soccer winner event has exactly three markets (home team, away team, Tie), every baseball and tennis event exactly two. So their outcomes are exclusive and cover every result. Because Kalshi's flag only says "at most one outcome", the rule is now `GameInfo.sums_to_one`: exclusive **and** two outcomes, or three outcomes with one named Tie or Draw. Anything else (for example a futures market added to `SPORTS_SERIES`) is not scaled and not told to add up to 100%. Limit: a game that is postponed or voided is outside this rule (Kalshi settles those its own way).

## Tasks 6 and 7 detail: median and market comparison (FEAT-20261012-1626, FEAT-20261012-1627), for approval

Branch `feature/sports-games-list`. New module `app/research/predict.py` (median and spread) and `app/research/compare.py` (market comparison). As before, wiring into a run is task 10 (`FEAT-20261012-1628`); the early record (`FEAT-20261013-0906`) saves what these produce.

### Task 6: median and spread

- **Per outcome:** the median of the valid forecasters' probabilities; with exactly two valid forecasts the median is their mean. Also saved: `min`, `max`, `spread` (max minus min, in probability points), and each forecaster's own number with its framing.
- **Where the outcomes must add up to 100%** (`GameInfo.sums_to_one`), the medians are scaled to add up to exactly 100% (medians of separate vectors can add up to slightly more or less). The unscaled medians are kept next to the scaled ones.
- **Output:** a plain dict stored in `runs.prediction`: per outcome `{market_ticker, outcome, probability, median_raw, spread, min, max, forecasts: [{variant, probability}]}`, plus `forecasters_valid`, `dropped` (with reasons), `evidence` (`supported` or `none`), `supported_claims` (count). With no prediction (fewer than two valid forecasts) it stores `{"unavailable": reason}`; there is no quiet substitute.

### Task 7: market comparison

**What the market gives us (verified live on 2026-10-13, public read calls):** each outcome's market has `yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars` and the contract counts at the best bid and ask (`yes_ask_size_fp`, `yes_bid_size_fp`). `last_price_dollars` is not used (often stale or zero). Prices are in steps of one cent for the series checked.

**Executable price (what a bet could really be placed at):**
- Buy YES at the **YES ask**; buy NO at the **NO ask** (which is 1 minus the YES bid). A missing side (no ask, or an ask of 0 or 1 dollar meaning an empty book) means **no executable price** for that side; it is shown as such and never compared.
- The prices are fetched at comparison time with one `get_event` call (the same call the run start already uses), and the time is saved as `priced_at`. The forecasters never see them.

**Fees.** Kalshi's market data has no fee field; the fee type and a multiplier are on the **series** (`GET /series/{ticker}`): `fee_type` is `quadratic` or `quadratic_with_maker_fees` and `fee_multiplier` is 1 for 14 of our 15 series and **0.5 for MLB** (read live today). The formula for these types, from several third-party sources and **not yet confirmed from Kalshi's own fee schedule** (the page answered HTTP 429 and could not be read today): fee for one contract at price P = 0.07 × multiplier × P × (1 − P), rounded up to the next cent per order. We take the **taker** fee because buying at the ask is a taker trade (the maker rate, a quarter of it according to some sources, applies only to resting orders and is not assumed). The fee is computed for one contract and is not rounded (rounding applies per order, which depends on size). If the series call fails, the comparer uses `quadratic` with multiplier 1 **and says so** (`fee_source: "assumed"`, logged), never silently.

**Per outcome, both sides are compared:**
- YES: `net edge = probability − yes_ask − fee(yes_ask)`.
- NO: `net edge = (1 − probability) − no_ask − fee(no_ask)`.
- The side with the larger net edge is the candidate; the other side's number is kept for display. The edge is per contract in dollars (0.05 = five cents of expected profit per contract, before any other cost).
- Saved with it: the bid, ask and sizes, `priced_at`, `fee_type`, `fee_multiplier`, `fee_source`.

**"Meaningful gap" (a flag, never an instruction).** All of these must hold for the candidate side:
1. net edge of the **median** is at least `EDGE_MIN` (default **0.05**, a placeholder);
2. the **worst-case forecaster** still shows a positive net edge on the same side (for YES the lowest forecast, for NO the highest). This is what "the forecasters agree" means, and it replaces a separate spread limit; the spread is still shown;
3. the evidence is not thin: `evidence` is `supported` and at least `MIN_SUPPORTED_CLAIMS` supported claims (default **5**, placeholder);
4. the best ask has at least `MIN_ASK_SIZE` contracts (default **10**, placeholder), so the price is not for one contract.
Any failed condition is listed by name next to the flag ("worst-case forecaster shows no edge", "only 3 supported claims"), so the page can say why. **The three thresholds are placeholders**: Milestone 4 replaces them with values chosen from scored forecasts. Until then a flag means "worth a person's look", nothing more.

**Not in this task:** sizing (how much to bet), orders, comparison for non-winner market types (FEAT-20261013-0907), alerts.

**Settings (defaults, in `.env.example` and compose):** `EDGE_MIN` 0.05, `MIN_SUPPORTED_CLAIMS` 5, `MIN_ASK_SIZE` 10.

**Tests (no network):** median of three and of two; unscaled and scaled medians; spread, min and max; no-prediction record carries the reason; NO ask equals 1 minus the YES bid; empty-book sides give no executable price; fee for sample prices (P 0.50 gives 1.75 cents at multiplier 1 and 0.875 at 0.5; P 0.10 and 0.90 give 0.63 cents); YES and NO edges and choice of side; each flag condition failing on its own with its named reason, and all passing; assumed-fee fallback is marked and logged; the comparer never receives forecaster text and the forecasters' prompt never receives prices (already tested for the prompt).

**Limits to state to the client:** the fee formula is from secondary sources until Kalshi's schedule can be read; the thresholds are placeholders; edge per contract ignores that large orders move the price (only the best level is used).

### Tasks 6 and 7 result (2026-10-13)

Built as specified: `app/research/predict.py` (median, spread, scaling, no-prediction record), `app/research/compare.py` (executable prices, fee, both sides, worst-case forecaster, named reasons), `KalshiClient.get_series`, three settings (`EDGE_MIN`, `MIN_SUPPORTED_CLAIMS`, `MIN_ASK_SIZE`, placeholders). 346 backend tests pass.

**Live read-only check (2026-10-13, public calls):** on a real MLB event the comparer read the series fee (`quadratic_with_maker_fees`, multiplier 0.5), the real bid, ask and sizes, and computed both sides. The probabilities used were invented for the check, so its output says nothing about opportunities.

**Observation for the opportunities screen (FEAT-20261013-0908):** in a two-outcome game, "buy YES on A" and "buy NO on B" are almost the same bet, so both outcomes of one game are flagged together (same edge in the check above). The screen must show one opportunity per game, not two.

## Early record of every forecast (FEAT-20261013-0906), for approval

Branch `feature/sports-games-list`. This answers the client's main question (can the system consistently find genuine opportunities?) from the first working forecast on, with no hindsight in the data: only **live** forecasts are recorded, each with the market price at that moment, and the real result is added when the game ends.

### What is recorded: one row per run and outcome, in a new table `outcome_records`

- **Identity and time:** `run_id`, `event_ticker`, `market_ticker`, `outcome` (title), `game_start` (from the game's milestone), `created_at`, and `before_start` (true when the record was made before the game started; the scoring uses only these, so in-play prices and results cannot leak in). Unique on (`run_id`, `market_ticker`).
- **Our forecast:** `probability` (the median), `min`, `max`, `forecasters_valid`, `evidence`, `supported_claims`.
- **The plain-AI baseline:** `baseline_probability`, from **one extra forecaster call with no claims and no research** (the same prompt and model, an empty fact list, the first framing). This is the "plain single AI call" of the Milestone 4 comparison; it costs about a cent per game. Setting `RECORD_BASELINE` (default true) switches it off; if the call fails the field is empty and the failure is logged, never replaced by a guess.
- **The market at that moment:** `yes_bid`, `yes_ask`, `no_ask`, `yes_ask_size`, `yes_bid_size`, `priced_at`, `fee_type`, `fee_multiplier`, `fee_source` (what the comparer read).
- **What our rule said then:** `side` (`yes` or `no` or none), `net_edge`, `worst_case_edge`, `meaningful`, `reasons`.
- **The result (filled in later, the only fields that ever change):** `resolved_at`, `resolved_yes` (true or false), `settlement_value`.

`runs.prediction` stays the display payload for the result page. The records table is the frozen, easy-to-query copy for scoring. A record is **never edited** except for the three result fields (code has a single update path, tested).

### Getting the result (verified live on 2026-10-13, public read calls)

A finished market has `status` `finalized`, `result` `yes` or `no`, `settlement_value_dollars` `1.0000` or `0.0000` and `settlement_ts`; an open one has `status` `active` and `result` empty. `GET /markets?tickers=A,B,...` returns many markets at once. Example seen today: Atalanta vs Venezia, Atalanta market `yes`, Tie market `no`. A market that was voided or settled at another value (for example a postponed game) is recorded as it is (`settlement_value` between 0 and 1) and **left out of the scores**, with a count shown.

### Two commands (added to `app/cli.py`, run like `check-kalshi-key`)

1. `resolve-records`: finds records without a result whose game started more than 3 hours ago (a setting, `RESOLVE_AFTER_HOURS`), asks Kalshi for those markets in batches, and fills in the result for the finalized ones. Safe to run again and again; prints how many were resolved and how many are still open.
2. `score-records` (optional `--since DATE`): over resolved records made before the game started, prints
   - the number of games and outcomes;
   - the **Brier score** (mean squared error, lower is better) of: our probability, the plain-AI baseline, and Kalshi's price (the middle of the YES bid and ask at the time; records with no two-sided quote are left out of that line and counted), all on the **same** records;
   - for records flagged as a meaningful gap, and for all records: the number, how often the chosen side won, and the **paper result per contract** (what buying the chosen side at the ask would have paid: win 1 dollar, minus the price, minus the fee), average and total;
   - a clear line when there are fewer than about 30 games: "too few to conclude anything". No verdict is printed; the numbers are shown, with the number of games next to each.
   Nothing here sizes a bet or places an order.

### Where records come from

`save_records` is called at the end of a run by the wiring task (FEAT-20261012-1628), after the comparison. Until then, tests and a small helper create them. Records only exist for games that were researched, so the sample is the games the client or the later scanner chose to run; a record is made for every outcome of the game, flagged or not, so the scores are not limited to the flattering ones.

### Honest limits

- Few games at first: a run costs real money and takes time, so the early numbers are small. The sample builds as runs accumulate (the later opportunities screen and monitoring items will produce many more).
- Brier scores of 25 games say very little; the command says so.
- The Kalshi price used is the mid of bid and ask when the forecast was made; a person trading would pay the ask and the fee, which is why the paper result uses the ask.
- The baseline uses the same model as the forecasters, so it tests "does research and checking help", not "does AI beat the market".

### Settings, tests, migration

Settings: `RECORD_BASELINE` (true), `RESOLVE_AFTER_HOURS` (3). One Alembic migration (autogenerated, reviewed). Tests: a record per outcome with the market snapshot and the rule's verdict; unique per run and outcome; `before_start` true and false; baseline stored, switched off, and failed; the only update is the result fields (a record cannot be rewritten); resolve with `yes`, `no`, still open, voided, and a Kalshi failure; running resolve twice changes nothing; the batch call uses `tickers`; scoring on a hand-worked set (Brier of each line, paper result, hit rate) with fake records; records made after the start, unresolved and voided ones excluded and counted; fewer than 30 games prints the warning; records with no two-sided quote are excluded from the market line only.

### Early record result (2026-10-13)

Built as specified: table `outcome_records` (migration `bcb93ee9b6b9`), `app/research/records.py` (`build_records`, `save_records`, `resolve_records`, `score_records`, `format_report`), `run_baseline` in `forecast.py`, commands `resolve-records` and `score-records` in `app/cli.py`, settings `RECORD_BASELINE` and `RESOLVE_AFTER_HOURS`. 365 backend tests pass; scoring is tested on a hand-worked set.

**Found while testing:** a record for a flagged outcome (empty list of reasons) was given the reason "no market snapshot", because an empty list was read as missing. Fixed and covered by the first record test. Lateral check: the same "empty list counts as missing" pattern does not occur elsewhere in the new modules (the other `or` fallbacks are on values that cannot be empty when valid).

**Not yet wired:** nothing calls `save_records` yet; that is task 10 (FEAT-20261012-1628). Run the two commands from `backend/` after `set -a; source ../.env; set +a`, as for `check-kalshi-key`: `uv run python -m app.cli resolve-records` and `uv run python -m app.cli score-records [--since 2026-10-13]`.

## Task 10 detail: connecting the steps into one run (FEAT-20261012-1628), for approval

Branch `feature/sports-games-list`. After this task, pressing Research on a game runs the whole pipeline and the API returns every part of its result. The result **pages** are task 1629.

### The run, stage by stage

`research` (planner and researchers, as now) → `fetch` (read the cited pages) → `check` (label each claim) → `forecast` (three forecasters and the plain-AI baseline, at the same time) → `compare` (median, fresh market prices, fees, flag) → record (save the early records) → `done`. The run's `stage` column is set when each stage starts, so the page can show progress. The run is `running` throughout, and counts against `MAX_CONCURRENT_RUNS` as a whole.

### Decision: sequential code after the research graph, not more graph nodes

The new stages run one after another in `execute_run` (`app/research/runner.py`) after the existing LangGraph research graph returns. **Why:** each stage already saves its result in the database (pages, checks, forecasts, prediction, records), a restarted run is marked failed and not resumed, and the stages do not fan out; so graph checkpoints would add moving parts and no recovery we use. **Rejected:** making every stage a graph node (one LangSmith tree and resumable runs, which we do not use). Cost of this choice: LangSmith shows the research graph as one trace and each later OpenAI call as its own trace (the client wrapper already traces them); `docs/agent/GRAPHS.md` is updated to say so.

### Failure rules (visible, never silent)

- **Research fails or finds nothing:** the run fails, as today.
- **Any later stage fails** (fetching, checking, forecasting, prices): the run stays `done` (the research is still worth reading) and `prediction` says `{"unavailable": "<stage> failed: <reason>"}`, with the details in the log. A stage never turns into a quiet default.
- **Fetching or checking switched off** (`FETCH_ENABLED=false` or `CHECK_ENABLED=false`): the run stops after research with `prediction.unavailable` = "Source checking is switched off (FETCH_ENABLED, CHECK_ENABLED)". Forecasting without checked evidence would hide that the evidence was not checked.
- **No supported claims:** the pipeline continues; forecasters run from the base rate and the evidence is marked `none` (as specified for task 5), so the comparer cannot flag.
- **Fewer than two valid forecasts:** `prediction.unavailable` with the reasons; the baseline and the research are kept; no records are written (nothing to score).
- **Kalshi prices unreadable:** the prediction is kept, `comparison.unavailable` says why, and the records are still written without a market snapshot (so the forecast can be scored against the result later; the market line of the score leaves them out).

### Cost, limits, time

- All model calls count in the run's token and cost totals and in the `RUN_COST_WARN_USD` flag: planner, researchers, checker, forecasters and baseline. The run also stores a **cost per stage** (`result.costs`: research, check, forecast, baseline) so the page can show where the money went. A model missing from the price table still gives "no price known", as now.
- Page limit: `FETCH_MAX_PAGES_PER_RUN` (25) as built; pages beyond it stay `not_fetched` and their claims `could_not_check`, and the run says how many were left out.
- Expected time: research 30 to 50 s (measured) plus fetching 10 to 30 s, checking 15 to 30 s, forecasting 30 to 60 s, so roughly one and a half to three minutes per game (unmeasured; to be measured on the first full run).
- Expected cost: about 40 cents for research (measured 26 to 33 cents), about 8 cents checking, about 2 to 3 cents for the forecasters and 1 cent for the baseline (unmeasured as a whole).

### What the API returns (`GET /api/runs/{id}`)

Adds to what exists: `stage`; `pages` (each cited link with `fetch_status`, `fetch_detail`, `fetch_method`, `http_status`, `fetched_at`; no page text); `claim_checks` (per claim and page: verdict and reason with its quotes); `prediction` (task 6's record with the comparison under `comparison`); `forecasts` (per forecaster: framing, reasoning, probability per outcome); `costs`. The list endpoint gets `stage` and a short summary (flagged outcomes count). Page text stays in the database and is not sent to the browser (size, and it is a copy of third-party pages).

### Code changes

`execute_run` gets the judge, the forecaster model, the Kalshi client and the fetch options as inputs (so tests use fakes); `create_app` builds the real judge and forecaster next to the research model; `app/runs.py` passes them through. `summarize` sums usages from all stages. No change to how a run is started or limited.

### Tests (all with fakes, no network, no key)

A full run from start to `done` with a fake research model, fake fetch transport, fake judge, fake forecaster and fake Kalshi: pages saved, checks saved, forecasts saved, prediction and comparison stored, records written, costs summed across all stages and per stage, `stage` seen in order (observed through a hook); each stage failing alone gives `unavailable` with the stage named while earlier results stay; switched-off fetch or check stops after research with the reason; no supported claims continues with evidence none; fewer than two forecasts; Kalshi down gives records without a snapshot; baseline failure leaves the baseline empty and the rest intact; the cost warning fires on the total; a stale run is still marked failed at startup; the API returns the new fields and no page text; existing run tests keep passing.

### Not in this task

Result pages (1629), more market types (0907), the opportunities screen (0908), monitoring (0909). Cached or repeated research of the same game is not added.


### Task 10 result (2026-10-13)

Built as specified: `app/research/pipeline.py` (stages, failure rules), `execute_run` restructured (`summarize` now sums every stage and stores a cost per stage; the run stays `running` until the last stage), `create_app` builds the real judge and forecaster next to the research model, `GET /api/runs/{id}` returns `stage`, `pages` (no page text), `claim_checks`, `forecasts`, `prediction`, `costs`, and the list returns `stage` and `flagged_outcomes`. 377 backend tests pass, including 12 whole-run tests with fakes for every outside service.

**Not yet done:** a run with the real OpenAI and Kalshi services. Until then the time (estimated one and a half to three minutes) and the total cost (estimated about 50 cents) are unmeasured. The running Docker stack is still the old build; rebuild with `docker compose up -d --build` to use this (a migration runs at start).

## Odds are market information, not forecaster evidence (BUG in TODO.md, approved by the user on 2026-10-13)

**Verified cause (first real run, notes D32):** the planner always plans an odds angle ("Current odds"); its claims are bookmaker prices. The checker treats them like any claim, and `supported_claims` passes every supported claim to the forecasters. So supported odds would reach the forecasters, although they must not see the market. (In that run the odds pages were all unreadable, which hid the problem.)

**Fix:**
1. `Angle` gets `kind`: `evidence` (default) or `market_odds`. The planner instructions say that the betting-odds angle must be `market_odds`; the kind travels with each finding in `runs.result`.
2. Code-side guard in case the planner mislabels: an angle whose name contains "odds" counts as `market_odds` too (explicit rule, one function).
3. `supported_claims` leaves out findings of that kind, so the forecasters never receive them. The claims are still fetched, checked and shown (their labels tell whether the odds pages could be read).
4. A rule in the forecaster instructions: if a fact states betting odds or a market price, ignore it as evidence. This covers odds that appear inside other angles' claims (the only protection for those; a regex for odds formats would be fragile and is not added).

**Not built here (logged as a separate deferred item):** using the odds as a benchmark (bookmaker prices with the margin removed) in the accuracy test.

**Tests:** planner prompt asks for the kind; findings carry it; `supported_claims` excludes `market_odds` and an angle named with "odds"; a whole run in which the odds claims are supported gives the forecasters only the other claims (and the supported count excludes them); the forecaster instructions carry the rule.

## Task 11 detail: the result pages (FEAT-20261012-1629), for approval

Branch `feature/sports-games-list`. Web app only (Next.js 16, shadcn components already in the project; the project has no automated web tests, so the checks are `npm run lint`, `npm run build` and headless-browser screenshots of real runs, as before). The run API already returns everything needed (task 10), except the small addition to the "latest run" call described under the Games list.

### 1. The result page (`/prediction/[runId]`, `components/run-view.tsx`), top to bottom

1. **Progress while it works:** one line per stage (Research, Read pages, Check claims, Forecast, Compare with the market) with the current one marked and finished ones ticked, from `stage`. The page still updates itself every 3 seconds. A failed or "unavailable" later stage shows a plain sentence at the top ("The forecast could not be made: <reason>") and the research below stays visible.
2. **The prediction table** (one row per outcome), with a one-sentence explanation above it: "Our probability is the middle of three independent forecasts that never saw Kalshi's price." Columns: **Outcome**; **Our probability** (median); **Range** (lowest to highest forecaster, the "spread"); **Market** (the price you would pay now for that outcome, in cents, with the side we compared: buying "yes" or buying "no"); **Gap** (net edge in cents per contract after fees, for the better side); **Flag**. A flagged row says "Worth a look" and nothing stronger; an unflagged row says in small text why not, in plain words from the named reasons ("only 2 supported claims", "the least favourable forecaster sees no gap", "no supported evidence", "too few contracts at that price"). Under the table: when the fee was assumed, say so; the time the prices were read; and "A flag is not a recommendation: its thresholds are placeholders until we have scored real forecasts." In a two-outcome game the two outcomes describe almost the same bet; a short note says so.
3. **Evidence** (what the forecasters were given): "x of y cited lines were supported by their page". Claims grouped by angle as now, each with a **check label** (Supported by the page / The page says something different / Could not check) and its reason, and the source links. The odds angle has its own heading, "Market prices found (not given to the forecasters)".
4. **Forecasters:** three collapsed cards (native `<details>`): the way each one worked in plain words ("Looked at each fact first", "Started from how often such sides win", "Argued against its first view"), its probability per outcome, and its reasoning text. The plain-AI baseline (the same question with no facts) is shown as a fourth line in the same table of estimates, so the effect of the research is visible. (The baseline's numbers are read from `outcome_records`; the run API returns them, see below.)
5. **Pages we tried to read:** a compact list: readable, or "could not read (blocked by the site, HTTP 403)", "needs JavaScript", "not a web page we can read".
6. **Side panel** as now, plus cost per stage and the stage the run reached.

The old closing note ("Cited does not mean checked ... no probability yet") is replaced by one that says what the labels mean.

### 2. The Games list

Each outcome row shows, next to the buy and sell prices, **our estimate** from the latest finished run for that game ("57% · forecast 2 h ago"), and a small "Worth a look" badge when that run flagged the outcome. A game with no forecast shows nothing extra. The header text is updated. Prices on the list are live (up to a minute old) while the estimate is from the time of the forecast, so the row shows the age, and the page says so. **Backend change:** `GET /api/runs/latest` also returns, for a finished run with a prediction, a compact `forecast` (per outcome: ticker, probability, flagged, and the time the prices were read); no page text, no reasoning.

### 3. The run list (`/prediction`)

A **Stage** column text for running runs, a **Flagged** column (count of "worth a look" outcomes, a dash when no forecast), and a corrected description ("Research and forecast runs").

### Backend additions

`GET /api/runs/{id}` also returns `baseline` (probability per outcome from the plain-AI call, from `outcome_records`), and `GET /api/runs/latest` returns the compact `forecast` above. Tests: both fields present, absent when there is no prediction, no page text anywhere.

### Plain-English labels (so the page never shows internal words)

Framings: `evidence_first` "Looked at each fact first", `base_rate_first` "Started from how often such sides win", `devils_advocate` "Argued against its first view". Checks: `supported` "Supported by the page", `not_supported` "The page says something different", `could_not_check` "Could not check". Fetch statuses: `ok` "Read", `blocked` "Not allowed to fetch", `empty_js` "Needs JavaScript or has almost no text", `unsupported` "Not a web page we can read", `too_large` "Too large", `failed` "Could not read (reason)", `not_fetched` "Not fetched".

### Accessibility and phone layout

Meaning is never colour alone (labels in words); tables scroll sideways on a phone; the prediction table collapses to stacked rows under 640 px; the existing 1120 px content width is kept.

### Not in this task

Approval buttons, charts, the opportunities screen (FEAT-20261013-0908), monitoring (0909), automated web tests (still a small open item; they would need a new test dependency, which would be asked first).


### Task 11 result (2026-10-13)

Built as specified: `components/prediction-table.tsx`, `forecasters.tsx`, `evidence.tsx`, `lib/labels.ts` (plain-English names), `run-view.tsx` reorganised (progress, forecast and comparison at full width, then evidence, pages, side panel with cost per stage), Games list estimates with their age, run list with stage and "Worth a look" count; backend `baseline` on a run and `forecast` in `/api/runs/latest`. Lint and build pass; 385 backend tests pass. Checked with headless-browser screenshots of a real run (Atletico vs Manchester United) on desktop and phone width and of the Games page. A first screenshot showed the six-column table squeezed by the side panel with its Flag column cut off; the forecast and comparison now use the full width.

**Second real run (same day):** 92 seconds, 0.43 USD (research 0.369, checking 0.034, forecasters 0.024, baseline 0.008). The planner marked the odds angle `market_odds` (checked live), so those claims were not given to the forecasters. Of 19 cited claims, 1 was supported, 2 were `not_supported` (correctly: the research had named players that the UEFA page listed differently), 16 could not be checked.

**Why so few were supported (reasons read claim by claim):** pages that are menus with no content (UEFA form guide, Manchester United fixtures); two UEFA match-history PDFs ("content type application/pdf cannot be read yet"); one page where the judge said supported but its quotes lacked a number of the claim (the number rule again); claims that bundle several details where the page shows only some ("does not name Hancko", "does not say Manchester or round of 16"); the odds pages blocked or empty. So real-world recall is far below the 7 of 9 on the hand-labelled sample, and the research's long compound claims make it worse. Candidate remedies, none built: ask the researchers for one fact per line; read PDFs (needs a new package); let a claim be supported in part; a table-aware text extraction. They are to be chosen with the user.
