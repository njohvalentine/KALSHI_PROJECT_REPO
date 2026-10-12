# TODO

- [x] FEAT-20261012-0951 — Project skeleton: Docker Compose (db, backend, frontend), validated settings, health endpoint (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md) [2026-10-12 09:53]
- [x] FEAT-20261012-0952 — Database tables and Alembic migrations: users, sessions, forecasts, source pages (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md) [2026-10-12 09:55]
- [x] FEAT-20261012-0953 — Single-user sign-in: account creation script, login, logout, protected endpoints (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md) [2026-10-12 09:57]
- [x] FEAT-20261012-0954 — Kalshi read-only client and market endpoints (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md) [2026-10-12 09:59]
- [x] FEAT-20261012-0955 — LangSmith tracing setup and LangGraph Postgres saved-progress setup (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md) [2026-10-12 10:18]
- [ ] FEAT-20261012-0956 — Web app shell: shared layout, login page, markets list with real data (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md)
- [ ] FEAT-20261012-0957 — Kalshi key check script: tells demo from production (spec: docs/specs/FEAT-20261012-0951-milestone-1-foundation.md)
- [x] BUG-20261012-0959 — Login failure counter can be bypassed by parallel login attempts: the counter is read, increased and written back without a lock, so simultaneous wrong passwords can undercount and delay or skip the lockout (found in security review of FEAT-20261012-0953; spec: docs/specs/BUG-20261012-0959-signin-review-findings.md) [2026-10-12 10:01]
- [x] BUG-20261012-1000 — Changing a password with the account script leaves already signed-in sessions valid, so an old (possibly stolen) session keeps working after a password reset (found in security review of FEAT-20261012-0953; spec: docs/specs/BUG-20261012-0959-signin-review-findings.md) [2026-10-12 10:01]
