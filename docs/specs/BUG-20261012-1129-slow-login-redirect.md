# Spec: signing in feels slow (BUG-20261012-1129)

Branch: `master` (base: `master`). Reported by the user: the login call answers at once but the redirect to the markets page happens after 3 seconds or more.

## Verified causes (measured on the compose stack with a mock Kalshi that answers in 1.5 seconds)

- Login call 0.09 s; `/auth/me` 0.008 s; `/api/runs/latest` 0.009 s. The markets page took 1.6 s: the page waits for Kalshi's answer and shows nothing meanwhile (`frontend/app/(app)/markets/page.tsx` awaits the Kalshi list before returning any HTML). With a real Kalshi slower than 1.5 s, the wait is that much longer.
- In a browser, one login produced **two** `/markets` page requests and **two** Kalshi calls: `login-form.tsx` calls `router.replace("/markets")` and then `router.refresh()`, and the refresh asks for the same page again. (They ran in parallel, so this doubles load on Kalshi and does not double the wait, unless Kalshi throttles.)
- The two lookups on the markets page (Kalshi list, then latest runs) run one after the other, not together. The second is fast, so this is minor.
- I do not know the real Kalshi response time from the user's machine; the backend does not log it. That is a fourth gap: nothing shows where the time goes.

## Fix

1. The markets page renders its title and description at once and streams the table inside a `Suspense` boundary with a visible loading state ("Loading markets from Kalshi"). Navigation then feels immediate; the table appears when Kalshi answers. The two lookups run together.
2. Remove `router.refresh()` after `router.replace` in the login form (and the same pairing in sign-out). Check in a browser that the signed-in page still loads correctly after login and after sign-out (the reason it was there: the router's cache of the earlier redirect).
3. The backend logs how long each Kalshi call took (path and milliseconds), so the real latency can be read from `docker compose logs backend`.

Not changed: caching the Kalshi list in the backend. Without the real latency it is a guess; the new log line tells us whether it is worth adding.

## Lateral check

Other pages that wait on slow data before showing anything: the prediction list and run page call only our own backend (milliseconds). The sign-out button has the same replace-plus-refresh pairing and is fixed in the same way. No other Kalshi-dependent page exists yet.

## Tests

- Backend: a Kalshi call logs its path and duration (unit test with a mock transport).
- Web app: build and lint pass; in a browser against the slow mock, the page title and a loading state appear immediately, the table appears after Kalshi answers, the login makes exactly one `/markets` page request and one Kalshi call, and sign-in, sign-out and a second sign-in all land on the right pages.
