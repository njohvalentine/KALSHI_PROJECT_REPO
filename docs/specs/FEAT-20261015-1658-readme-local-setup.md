# Spec: a README for local setup

Branch `feature/sports-games-list` (base `master`). Asked for by the user on 2026-10-15; plan approved by the user as "local setup only". Documentation only: no code, no dependency, no `.env` written.

## Why

The repository has no `README.md`. The setup facts exist, but spread over `docs/RUNBOOK.md` (written for the person who runs the system day to day). Someone who has just cloned the project has no single place to start.

## Design

- One file, `README.md`, at the top. Short: setup first, the rest by link to `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`, `docs/MILESTONES.md`, `docs/ACCURACY-REPORT-2026-10-15.md`, `docs/DEMO.md`. It does not copy the runbook.
- Contents: what the project is (nothing real is ever ordered); what to install (Docker with Compose, a VPN if Kalshi is not reachable, an OpenAI key; Node 24 and Python 3.13 with `uv` only for tests on the host); setup steps (copy `.env.example` to `.env`, fill in the required values, `docker compose up -d --build`, create the first account with the CLI, open `http://127.0.0.1:3000`); the checks (`/health`, tests, browser tests); the secrets rules.
- Every command and value is taken from `docs/RUNBOOK.md`, `.env.example`, `docker-compose.yml` and the Dockerfiles, not from memory. The required settings follow the runbook: `POSTGRES_*`, `KALSHI_API_BASE`, `SESSION_SECRET`; `OPENAI_API_KEY` is needed for research only.
- Local only: no server, no TLS, no deployment advice (`SESSION_COOKIE_SECURE=false` is said to be for plain-http local use, as in `.env.example`).
- It never tells anyone to write `.env` by a generator in the repo; the person edits the file by hand.

## Not done

No deployment guide, no copy of the runbook, no code changes.

## Checks to state at close

Lateral spread: the commands in the README are compared with the runbook so the two do not disagree. Causal depth: the need is "a newcomer can start the project from a clone"; the README is followed step by step where it can be (compose config, health URL) without touching `.env`.
