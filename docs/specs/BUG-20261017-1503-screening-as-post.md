# Spec: the free bookmaker check must be a POST with the guard header

Branch `feature/sports-games-list` (base `master`). Found by an automated security review of the commit of FEAT-20261017-1127 on 2026-10-17; verified by reading the code.

## What is wrong (verified)

`GET /api/games/screen` reads the odds feed (up to `SCREEN_MAX_LEAGUES` credits of the free monthly allowance) and saves rows in `screenings`; the Games page triggers it from the address `/games?screen=1`. The session cookie is `SameSite=Lax`, which browsers send on a top-level navigation by GET from another site, so a link on any website can make a signed-in person's browser run it. The damage is small (at most 8 credits, repeated presses are served by the 10-minute cache, and the saved rows are harmless), but it is a state-changing GET, and the rest of the app does not have one: I listed every GET route (`auth/me`, opportunities, orders, games, alerts, dashboard, runs, health) and none writes to the database or spends a paid allowance. Other routes that change state are POSTs guarded by `require_requested_with`.

## Design

- **The route becomes `POST /api/games/screen`** with the `require_requested_with` dependency, like the other actions (a browser will not add a custom header to a cross-site request without our consent). A GET to the same path answers 405.
- **The page keeps its link, but the link no longer does the work.** `/games?screen=1` (a plain GET) now only shows a button "Check these games against the bookmakers" that, when pressed, sends the POST from the browser and shows the labels. So the results are held in the page (a small client component with the labels in its state), not in the address. Pressing it again within 10 minutes costs no credits (the feed cache); a reload forgets the labels, and pressing again is free inside the cache time.
- The Games page server code no longer calls the check; it only says whether the check is available and the limits.
- **Not changed:** the rule, the credit floor, the league limit, what is saved.
- Tests: the POST works and saves rows; the POST without the header answers 403; the GET answers 405; a request without a session answers 401; the browser test checks the button is offered, that loading `/games?screen=1` does not run the check (credits unchanged, no labels), and that pressing the button shows the labels (the answer mocked in the browser, which now works because the call is made from the browser).

## Not done

No per-user rate limit on the check: the credit floor, the league limit and the cache already bound the cost, and there is one account. A per-user limit can be added if more accounts appear.

## Checks to state at close

Lateral spread: every GET route re-listed after the change, none with a side effect. Causal depth: the cause is "a button implemented as a link"; the fix makes the action a POST with the guard header and keeps the cost bounds.
