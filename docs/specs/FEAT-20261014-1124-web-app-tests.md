# Spec: automated end-to-end tests for the web app (FEAT-20261014-1124)

Branch `feature/sports-games-list` (base `master`). For approval; nothing is installed or written yet. The dependency itself, `@playwright/test`, was approved by the user on 2026-10-14 ("add playright also").

## Why (the need behind the request)

The backend has 515 tests; the web app has none, only lint, build and manual checks. The web app now holds the part people use to take decisions: sign-in, the ticket builder (state kept across pages), the Approval flow. A break there is invisible to the backend tests (the 2026-10-14 browser check found two defects only because I drove it by hand). We need a few tests that drive a real browser through those flows and fail when they break.

## What I verified (2026-10-14; official docs and the npm registry, see the research notes in the session)

- Next.js 16's testing guide lists Playwright and recommends it for async server components and the proxy, which Vitest cannot test; it recommends running against `next build` and `next start`.
- `@playwright/test` is one npm dependency (it pulls `playwright` as its only dependency). It needs Node 20 or later (we have 24.18) and downloads its own Chromium into the user cache (`~/.cache/ms-playwright`, about 150 MB), not into the project and not as a global install. Playwright supports Ubuntu 22.04 and 24.04.
- Not verified: that the bundled Chromium starts on this laptop without extra system libraries (it will be tried as the first step; if system libraries are missing I stop and ask before installing anything with `sudo`).

## Design

1. **Dependency:** `@playwright/test` as a dev dependency of `frontend/` only, at the version the registry gives today (checked against the lock file), plus `npx playwright install chromium` (browser binary only, user cache).
2. **Where:** `frontend/e2e/*.spec.ts`, `frontend/playwright.config.ts`, script `npm run test:e2e`. Excluded from the production Docker image (the image copies the built app; the tests run from the host against the running stack, `http://127.0.0.1:3000`). `test-results/` and `playwright-report/` are git-ignored.
3. **Account:** a dedicated test user, created with the existing command (`create-user e2e@example.com`), whose address and password come from `E2E_EMAIL` and `E2E_PASSWORD` in the shell environment. The tests fail at the start with a clear message if they are missing (no default, no password in the repository). They never use the demo account.
4. **Data:** the tests run against the real local stack and its real database, so they must not depend on which games exist and must leave nothing behind: a test that needs a researched game skips itself with a plain reason when there is none ("no researched game with a price"); every ticket a test prepares is rejected by the test itself, also when the test fails (a `finally`/fixture teardown). No test places or approves anything, and the simulation cannot reach Kalshi anyway.
5. **The tests (about 6):**
   - sign in with a wrong password shows the message and stays on the login page; the right one reaches the Games page; signing out returns to the login page; a page behind login redirects to it.
   - Opportunities (all games) → add two legs from different games → the ticket panel shows two legs and the combined line.
   - the legs stay when moving to a run page; adding a second market of the same group replaces the first; adding two markets of one game shows the "rough" note.
   - Prepare ticket → the Approval page shows the legs and the checks → Reject → nothing is waiting (this also proves the cleanup works).
   - the Results page loads.
6. **Run:** `E2E_EMAIL=... E2E_PASSWORD=... npm run test:e2e` after `docker compose up -d`. Documented in the RUNBOOK (tests section).

## Not done

- Vitest and Testing Library for component tests (4 to 5 more dev dependencies; the flows above cover the client components): only if a component needs a test the browser tests cannot reach.
- Running the browser tests in CI or inside Docker, a fake backend, visual snapshots.
- Tests that place or settle tickets.

## Checks to state at close

Lateral spread: every page a person can reach (Games, Opportunities, Prediction, Approval, Results, Login) is touched by at least one test or named as not covered. Causal depth: the need is "catch a broken decision flow"; the flows with the most state (ticket builder, Approval) are covered; pages with only reading (Games list filters, run page evidence tables) are not, and the note says so.

## Result (2026-10-14)

Built as specified: `@playwright/test` 1.64.0 as the only new dev dependency (plus the browser binary in `~/.cache/ms-playwright`, about 120 MB, started without extra system libraries); `frontend/playwright.config.ts`, `frontend/e2e/` with 7 tests in two files (sign-in redirect, wrong password, sign in and out; the ticket kept across pages and removable; two markets of one game marked rough and a same-group market replacing the first; a prepared ticket waiting on the Approval page with its checks and rejected, with cleanup in a `finally`; the Results page); script `npm run test:e2e`; `e2e`, the config and the reports are left out of the Docker image (`.dockerignore`) and of git. All 7 pass against the running stack (which was built before the tests); the missing-credentials case fails with a clear message; lint and a local build are clean. The test account `e2e@example.com` was created with the existing command.

Not done or not measured: a rebuild of the frontend image with the new `package.json` was started but `npm ci` inside Docker was very slow (the network is slow with the VPN on) and was not finished at the time of this commit, so the image still running is the earlier one; no test was made to fail on purpose to prove it catches a break; the "prepared ticket" test skips itself when no game is open for a ticket (it ran and rejected a real ticket today). A linter rule made me name the fixture argument `provide` instead of `use`.

Checks done: lateral spread (Games, Opportunities, the run page, Approval, Results and Login are each touched; Opportunities has no test of its own, the builder is tested through the run pages because the Opportunities page shows add buttons only for flagged games); causal depth (the flows with the most state are covered; pure reading pages such as the Games filters and the evidence tables are not).
