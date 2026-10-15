# Spec: redesign step 3, the Dashboard

Branch `feature/sports-games-list` (base `master`). Step 3 of the redesign approved on 2026-10-15 (sample: `docs/design/mockup-redesign-2026-10-15.html`, first tab). Defaults agreed with the user: the Dashboard is the landing page after sign-in, and the message "No sign of an edge yet" is written by the app from the numbers.

## What is there now (read in the code)

- No page shows the scores. They exist only in the command `score-records` (`research/records.py: score_records`, which already computes all the numbers the sample shows: games, outcomes, Brier scores of ours, the plain AI and the market on the same outcomes, per sport, the flagged bets, the excluded counts).
- The landing page is Games: `app/page.tsx` redirects to `/games`, the sign-in form sends to `/games`, the header logo links to `/games`, and the browser test fixture waits for `/games` after signing in.
- The "worth a look" count is available from the existing `/api/opportunities` (it reads live Kalshi prices, so it is slow; the Opportunities page already waits for it behind a loading line).

## Design

**Backend** (new file `backend/app/dashboard.py`, one route `GET /api/dashboard`, login required, registered in `main.py` like the others; no database change, no new dependency, no model call):
- Calls the existing `score_records(engine, None, series, MIN_SUPPORTED_CLAIMS)`: the numbers cannot differ from the command's.
- Returns only what the page shows: games and outcomes scored; unresolved outcomes left out; Brier of ours, plain AI and Kalshi on the same outcomes (and how many outcomes); per sport: games, ours, plain AI, Kalshi (same outcomes); flagged bets (bets, won, average result per contract); the research spend (sum of `runs.cost_usd`, number of runs, and the sentence that the app calculates it from tokens and stored prices, so it is not the OpenAI bill); the games needed for a verdict (`MIN_GAMES`, 30).
- **The message** is written here, in one function, from the numbers (so it is tested and shown the same everywhere). Let `gain` be Kalshi's score minus ours (positive means we are better):
  - fewer than 30 games: "Only N games have finished: too few to say anything yet."
  - `gain` at least 0.005 (the bar the replay plan used): "Our forecasts are ahead of the Kalshi price by X on N games. This is not proof: look at each sport and keep scoring."
  - otherwise: "No sign of an edge yet. On N finished games our forecasts are not better than the Kalshi price (ours A, Kalshi B). N games is not a final verdict."
  - A sport row with fewer than 5 games is marked "too few games"; the flagged-bets card says "too few to read" below 30 bets.
- Scoring reads about 560 records in under a second today; it is computed on each request and not cached. If the table grows to tens of thousands, caching is the next step.

**Frontend:**
- New page `app/(app)/dashboard/page.tsx`: the message line, four number cards (games scored, worth a look today, flagged bets, research spend), a bar chart "Forecast error, all games" (ours, plain AI, Kalshi), and bars by sport, as in the sample. The bars are plain styled boxes, no chart library.
- "Worth a look today" reads `/api/opportunities` in its own loading section, so the rest of the page appears at once; if that call fails the card says so and the rest still works.
- Navigation: "Dashboard" is the first tab. The landing page after sign-in, the logo link and `app/page.tsx` point to `/dashboard`.
- The browser test fixture and the sign-in test wait for the Dashboard after signing in; one new test opens the Dashboard and checks the message line and the four cards are shown.

## Not done

No time filter, no per-league or per-evidence tables (the report has them), no caching, no changes to the scoring code, no bookmaker numbers (the benchmark is off).

## Tests

Backend `tests/test_dashboard.py`: records made with the same helpers as `test_records.py`: the endpoint's numbers equal `score_records`; the message for fewer than 30 games, for a gain of at least 0.005 and for no gain; a sport with fewer than 5 games is marked; sign-in is required (401 without a session); an empty database answers with zeros and the "too few" message, not an error. Frontend: lint, build, the browser tests, and desktop and phone screenshots.

## Checks to state at close

Lateral spread: every place that sends a person to `/games` after sign-in (page, form, logo, test fixture) is changed together; the other pages are untouched. Causal depth: the need is that the most important fact (how we compare with Kalshi) is visible at once and cannot be read more optimistically than the numbers allow; the message is written in one place from the numbers, and uses the same code as `score-records`.
