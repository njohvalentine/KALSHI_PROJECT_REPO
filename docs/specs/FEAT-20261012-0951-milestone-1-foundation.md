# Spec: Milestone 1, foundation (FEAT-20261012-0951 to FEAT-20261012-0957)

Branch: work lands on `master` (base: `master`; the repo has one docs commit and no remote yet). No branches are created by Claude.
Design decisions behind this spec are in `docs/discussion/NOTEPAD.md` (D3 to D19). This spec only covers how Milestone 1 is built.

## 1. What is being built

The system runs end to end on real data with nothing intelligent yet: a Docker Compose stack (backend, web app, Postgres), a single-user sign-in, a read-only Kalshi connection, saved-progress and tracing wiring, and a web shell that lists real Kalshi markets behind the login.

## 2. Verified current state (checked 2026-10-12)

- Repo: git on `master`, one docs commit, no code, no `TODO.md` before this work. Git identity is set (nodeexcel).
- Tools on this machine: Python 3.13.11, uv 0.9.5, Node v24.18.0, npm 11.16.0, Docker 28.4.0, Docker Compose v2.39.4.
- Package compatibility for Python 3.13 was checked on PyPI and by a dry-run resolve (NOTEPAD D13, D19): langgraph 1.2.14, langgraph-checkpoint-postgres 3.1.2, fastapi 0.143.0, psycopg 3.3.6, langsmith 0.14.5, openai 3.26.1, pwdlib 0.3.1 all resolve together.
- Next.js 16.4.0 needs Node >= 20.9 (docs), fine.
- **Limit of this environment:** the dev sandbox cannot reach `external-api.kalshi.com` (connection fails), while PyPI and npm work. The Kalshi client is therefore tested here against mocked responses only. Real calls must be tried once on a machine with access (the user's), before Milestone 2 relies on them.
- **Kalshi response field names are not verified.** Endpoint paths and parameters come from Kalshi's docs via search summaries (NOTEPAD D10). The client returns the response JSON unchanged and does not hard-code field names beyond pagination (`cursor`). Field names get pinned against Kalshi's OpenAPI spec (`docs.kalshi.com/openapi.yaml`) at the first real call.

## 3. Module 6 checks (greenfield)

- Lateral spread: not applicable, no existing code or siblings. Patterns set here (settings validation, endpoint protection) are written once and reused by later endpoints.
- Causal depth: the underlying needs are (a) one place that checks who is calling before anything sensitive, (b) fail loudly on bad config, (c) never hold secrets that a milestone does not need. Each task below addresses these; nothing else was found.

## 4. Layout

```
backend/            uv project (pyproject.toml, uv.lock), Python 3.13
  app/              FastAPI app: config, db, auth, kalshi, tracing
  alembic/          migrations (scaffolded with `alembic init`)
  tests/
frontend/           Next.js (scaffolded with create-next-app) + shadcn/ui
docker-compose.yml  db, backend, frontend
.env.example        every setting, no secrets
```

Scaffolding uses generators (CLAUDE.md Module 8): `uv init`, `alembic init`, `create-next-app`, `shadcn init`.

## 5. Dependencies (project-local only, Module 5)

Backend (installed with `uv add` into `backend/.venv`):
- Named and approved in discussion: `fastapi`, `sqlalchemy`, `alembic`, `psycopg[binary,pool]`, `pwdlib[argon2]`, `langgraph`, `langgraph-checkpoint-postgres`, `langsmith`.
- **Not named earlier, needed to run or test (flagged for the user):** `uvicorn` (runs FastAPI), `httpx` (Kalshi client, with mock transport for tests), `cryptography` (request signing in the key check script, FEAT-20261012-0957), `pytest` (dev only).
- Not installed in Milestone 1: `openai` (no model calls yet; the OpenAI key is not loaded).
Frontend: whatever `create-next-app` generates, plus shadcn/ui (approved).
Docker images: `postgres` and official `python` / `node` base images.

## 6. Tasks

### FEAT-20261012-0951 Project skeleton and Docker Compose
- `docker-compose.yml` with three services: `db` (Postgres, data in a named volume), `backend`, `frontend`. Backend waits for a healthy db.
- Settings module reads environment variables and validates at startup (Module 4). **Required, no defaults:** `DATABASE_URL`, `KALSHI_API_BASE`, `SESSION_SECRET`. `LANGSMITH_API_KEY` is required only when `LANGSMITH_TRACING=true`. Tuning knobs with safe defaults: `SESSION_TTL_HOURS` (12), `LOGIN_MAX_ATTEMPTS` (5), `LOGIN_LOCKOUT_MINUTES` (15), `SESSION_COOKIE_SECURE` (true; set false only for plain-http local use, logged at startup when false). Missing or invalid required settings stop the process with a message naming the setting.
- `GET /health` (no login) returns status and whether the db answers.
- `.env.example` lists every setting; `.env` is git-ignored.
- Secrets that are not needed in this milestone (`OPENAI_API_KEY`, Kalshi key and private key) are not read by the backend at all.
- Done when: `docker compose up` starts all services; `/health` is ok; starting the backend with a required setting removed fails with a clear message (test).

### FEAT-20261012-0952 Database and migrations
- SQLAlchemy models and an Alembic migration (first revision) for: `users` (id, email unique, password_hash, failed_attempts, locked_until, created_at); `sessions` (id, user_id, token_hash unique, expires_at, created_at); `forecasts` (id, run_id, market_ticker, probability, kalshi_price, created_at, outcome nullable); `source_pages` (id, run_id, url, title, retrieved_at, content_hash, content).
- `forecasts` keeps history (many rows per market) for re-checks (NOTEPAD D15). `kalshi_price` stores the price at forecast time.
- The LangGraph checkpoint tables are created by its own `setup()` (FEAT-20261012-0955), not by Alembic.
- Done when: `alembic upgrade head` on an empty Postgres creates the tables; `alembic downgrade base` removes them (test on the compose db).

### FEAT-20261012-0953 Sign-in (single user, accounts made by script)
- Passwords hashed with Argon2 via `pwdlib` (`PasswordHash.recommended()`). Plain passwords are never stored or logged.
- `python -m app.cli create-user <email>` asks for the password without echo (or reads it from stdin), stores the hash. Also `set-password`. No register endpoint.
- `POST /auth/login`: checks credentials; for an unknown email still runs a hash against a dummy hash so timing does not reveal which emails exist; after `LOGIN_MAX_ATTEMPTS` failures the account is locked for `LOGIN_LOCKOUT_MINUTES`; the response is the same generic error for unknown email, wrong password and locked account. On success it creates a random session token, stores only its hash, and sets it as an `HttpOnly`, `SameSite=Lax` cookie (`Secure` per setting) that expires after `SESSION_TTL_HOURS`.
- `POST /auth/logout` deletes the session. `GET /auth/me` returns the signed-in email.
- A reusable dependency `require_user` rejects missing, expired or unknown sessions with 401. Every endpoint except `/health` and `/auth/login` uses it.
- State-changing requests (POST) also require a custom header `X-Requested-With` as a basic cross-site request guard on top of `SameSite=Lax`; the exact scheme gets re-checked when the approve endpoint is built (NOTEPAD D19).
- Done when tests pass for: login success, wrong password, unknown email (same response), lockout after N failures, expired session, logout, protected endpoint without a session, password never appearing in the database or logs.

### FEAT-20261012-0954 Kalshi read-only client
- A small `httpx` client against `KALSHI_API_BASE` with no Kalshi credentials (public reads, per Kalshi docs): `list_markets(status, limit, cursor, ...)`, `get_market(ticker)`, `get_candlesticks(series_ticker, ticker, start_ts, end_ts, period_interval)`, `get_historical_cutoff()`, `list_historical_markets(...)`, `get_historical_candlesticks(ticker, start_ts, end_ts, period_interval)`.
- Backoff and retry on HTTP 429 and connection errors; every retry is logged with its reason (Module 4, no silent fallback). Gives up after a fixed number of tries and raises.
- Returns Kalshi's JSON unchanged (see section 2 on unverified fields).
- Backend endpoints (login required): `GET /api/markets` and `GET /api/markets/{ticker}`.
- Done when: unit tests with a mock transport cover success, pagination cursor pass-through, 429 then success, 429 until give-up, and the login requirement. **Not verified against the live Kalshi API in this environment.**

### FEAT-20261012-0955 Tracing and saved progress
- Startup: if `LANGSMITH_TRACING=true`, require `LANGSMITH_API_KEY` and fail loudly if missing; the settings are passed to the environment LangSmith reads. If false, log that tracing is off.
- A function that opens the LangGraph Postgres checkpointer (`AsyncPostgresSaver`) from `DATABASE_URL` and runs its `setup()`, used at app startup. Pool settings follow LangGraph's documented requirements (autocommit and dictionary rows) and are confirmed against the installed version's docs at build time.
- No graph yet.
- Done when: the checkpoint tables exist after startup (test on the compose db); a deliberate bad `DATABASE_URL` fails at startup.

### FEAT-20261012-0956 Web app shell
- `create-next-app` (TypeScript, Tailwind, App Router, ESLint) in `frontend/`, then `shadcn init`.
- One shared layout with a single content width (1120px) and the design tokens from `docs/design/mockups.html` (colors, type, spacing). Header with the four nav items and a sign-out.
- Pages: `/login`; `/markets` (real data from the backend: question, close time, current price); the other three pages exist as empty placeholders in the same layout.
- Requests to the backend go through Next.js rewrites on the same origin so the session cookie works without cross-origin settings. Unauthenticated visits redirect to `/login` (convenience only; the backend check is the protection).
- Font: Schibsted Grotesk through `next/font`.
- Done when: in the compose stack a user created with the script can sign in, sees the markets list rendered by the real backend path (with mocked Kalshi data in tests), is redirected to login when signed out, and the page width is identical on every page (checked by screenshots at 1280px and 390px).

### FEAT-20261012-0957 Kalshi key check script
- `python -m app.cli check-kalshi-key` reads `KALSHI_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` from the environment (only this command reads them), signs `GET /trade-api/v2/portfolio/balance` (RSA-PSS SHA-256 or Ed25519 depending on the key file, signature over timestamp + method + path without query), sends it to the demo host, then the production host, and prints which one accepts it. Read-only; never sends an order. Never prints the key, the signature or the balance amount (only "works / does not work" per environment).
- Hosts are settings (`KALSHI_DEMO_API_BASE`, `KALSHI_API_BASE`), no hidden defaults.
- Done when: unit tests verify the signature against the generated key's public part for both key types and the output never contains secret material. **Not run against Kalshi in this environment.**

## 7. Order of work and commits

0951, 0952, 0953, 0954, 0955, 0956, 0957. One commit per task (docs/TODO updates in the same commit that closes the item). TODO markers: `[ ]` to `[o]` when a task starts, to `[x]` with the completion time when its commit lands.

## 8. Out of scope

Agents, model calls, web search, the approval flow, order placement, the results page content, HTTPS in front of Compose, password reset by email, multiple users.

## 9. Deviations and notes recorded during the build (2026-10-12)

- **Module layout:** the backend is a plain uv app with a top-level `app/` package (not an installable package), as the layout in section 4 says.
- **`httpx2` instead of `httpx`:** Starlette's test client now warns that `httpx` is deprecated and asks for `httpx2` (the maintained successor, same API). It replaces `httpx` in the dependency list in section 5 and is also what the Kalshi client uses.
- **Checkpoint setup lock:** LangGraph's table setup uses `CREATE INDEX CONCURRENTLY`, so starting several processes at once deadlocked. Startup now takes a database-wide advisory lock by polling `pg_try_advisory_lock` (never blocking inside a statement), see `backend/app/checkpoint.py`.
- **Web app generator defaults changed:** `create-next-app --yes` turned on Cache Components and partial prefetching. They are switched off in `frontend/next.config.ts`: every page depends on the signed-in cookie and live data, so there is nothing to cache.
- **Dependency added by the shadcn generator:** its template imports class-name helpers from an npm package called `cn` (plus `@base-ui/react`, `class-variance-authority`, `lucide-react`, `tw-animate-css`). These came from the approved `shadcn init`, not from a separate choice.
- **Proxy rewrites are fixed at build time:** `BACKEND_INTERNAL_URL` is passed to the web image as a build argument as well as a runtime setting.
- **Paper-trading banner is static text** in this milestone, because no order feature exists yet. When orders are built, the banner must read the real mode from a setting.
- **Markets page fields** (`title`, `subtitle`, `close_time`, `last_price_dollars`) follow Kalshi's docs (as summarized by search, about three months old) and were exercised with a mock Kalshi only; they are read defensively and shown as a dash when missing.
- **Only the first 50 open markets are listed;** paging comes later.
