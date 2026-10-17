# Valentine: AI research assistant for Kalshi sports markets

An app that researches a sports game, gives a probability for each outcome, and compares it with the Kalshi price. A person approves every bet. **Nothing real is ever ordered:** Kalshi is only read, and the approval screen places simulated orders only.

So far the forecasts are not better than the Kalshi price. See `docs/ACCURACY-REPORT-2026-10-15.md`.

This file is for setting the project up on your own computer. Day-to-day use is in `docs/RUNBOOK.md`.

## What you need

- Docker with Docker Compose. This runs everything.
- An OpenAI API key, only for research. Without it the app starts and the Games page works, but pressing Research is refused.
- A VPN, if Kalshi is not reachable from your country.
- Only to run the tests on your own machine: Python 3.13 with [uv](https://docs.astral.sh/uv/), and Node 24 with npm.

## Set up

1. Copy the example settings file:

   ```
   cp .env.example .env
   ```

2. Open `.env` in an editor and fill in the values. Never commit `.env` and never paste it anywhere.
   - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: choose your own.
   - `DB_HOST_PORT`: the port on your computer for the database (used by the tests). Change it if 5432 is taken.
   - `KALSHI_API_BASE`: leave the production address from the example.
   - `SESSION_SECRET`: at least 32 random characters, for example the output of `openssl rand -hex 32`.
   - `SESSION_COOKIE_SECURE`: set to `false` for local use over plain http.
   - `OPENAI_API_KEY`: needed for research.
   - Everything else is optional and has a safe default. Each line in `.env.example` has a comment.

3. Start everything. The first build takes a few minutes. The database is set up when the backend starts.

   ```
   docker compose up -d --build
   docker compose ps
   curl http://127.0.0.1:8000/health
   ```

   All three services (`db`, `backend`, `frontend`) should be "Up" and the health answer should be `{"status":"ok","db":true}`. If the backend does not start, `docker compose logs backend` says which setting is wrong.

4. Make your first account. There is no sign-up page. The command asks for a password twice:

   ```
   docker compose exec backend uv run --no-sync python -m app.cli create-user you@example.com
   ```

5. Open http://127.0.0.1:3000 and sign in.

To stop: `docker compose down`. The data stays. `docker compose down -v` also deletes the database, so use it only on purpose.

## Run the tests

Backend, with the database from step 3 running. Use your own values from `.env`:

```
cd backend
TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:DB_HOST_PORT/DB_NAME uv run pytest -q
```

Frontend checks:

```
cd frontend
BACKEND_INTERNAL_URL=http://127.0.0.1:8000 npm run lint
BACKEND_INTERNAL_URL=http://127.0.0.1:8000 npm run build
```

The browser tests need extra steps (a test account and a browser download). They are in section 11 of `docs/RUNBOOK.md`.

## Secrets

- `.env` is git-ignored. Keep it that way.
- These are secrets: `OPENAI_API_KEY`, `SESSION_SECRET`, `POSTGRES_PASSWORD`, `LANGSMITH_API_KEY`, the Telegram bot token, the Odds API key and any Kalshi key.
- The app only reads Kalshi, so no Kalshi key is needed to run it.
- Backend logs can contain the Telegram token when alerts are on. Do not share logs.

## More

- `docs/RUNBOOK.md`: start, stop, settings, accounts, costs, alerts, scoring, backups, problems.
- `docs/ARCHITECTURE.md`: how it works.
- `docs/MILESTONES.md`: what is built and what is not.
- `docs/ACCURACY-REPORT-2026-10-15.md`: how good the forecasts are.
- `docs/RISK-FRAMEWORK.md`: the proposed limits and stop rules for 100 dollars in paper mode, and what would be needed before anything beyond paper.
- `docs/HOW-IT-WORKS.md`: what the system does, its agents, strategies and every term explained.
- `docs/DEMO.md`: a script for showing the app.
