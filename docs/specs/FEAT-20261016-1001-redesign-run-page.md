# Spec: redesign step 5b, the run page

Branch `feature/sports-games-list` (base `master`). Step 5b of the redesign, split off with the user on 2026-10-16. Frontend only: no backend change, no dependency (the native HTML `<details>` element does the folding, so it works without scripts).

## What is there now (read in `app/(app)/prediction/[runId]/page.tsx`, `components/run-view.tsx`, `prediction-table.tsx`, `forecasters.tsx`, `evidence.tsx`)

For a finished run the page shows, one after another and all open: the "not yet measured" notice, "Our forecast and the market" (one table for each kind of market, with a flag, a Prepare-order button and Add-to-ticket buttons on every row, and a long paragraph that explains the flag), "The forecasts" (a second table of all markets with the three forecasters, the median and the plain AI, then each forecaster's reasoning, already folded), then the evidence (every angle, every claim with its sources and verdicts), "Pages we tried to read", "What was researched", and a side box with the run's details and costs. For the NBA game (48 markets, 22 cited lines, many pages) the page is about 17,300 px tall at 1280 px wide. Nothing on it is wrong; there is too much at once, and nothing says what matters.

## Design (nothing is removed; things are folded or moved)

- **"At a glance" box at the top** (finished runs only), computed from the run's own data, no new request: how many markets are worth a look (and the best one, with its side, price and gap after fees, with a few more in a short list); "N of M cited facts were supported by their page"; how many forecasters gave a valid answer; the time taken and the cost. If nothing is flagged it says so, with the most common reason from the run. The "not yet measured" notice stays directly above it.
- **Our forecast and the market:** stays first and open, but the kinds of market (who wins, total, margin, both teams to score) become folds: the first kind is open; each other kind is closed, with a summary line "Total goals, runs or points: 24 markets, 3 worth a look". The flag's long explanatory paragraph moves into a closed fold "How a market gets the flag". The notes about prices, fees and adjustments stay visible under the table.
- **Closed by default, with a one-line summary each:** "The forecasts" (three forecasters, the median and the plain AI side by side), "The evidence" (N of M facts supported), "Pages we tried to read" (N pages, K read), "What was researched" (N angles). The explanation under "The evidence" stays inside its fold.
- **Always visible:** failed or running run messages, "Angles that did not finish" (short), and the side box with the details and costs.
- A small shared component `components/fold.tsx` (a styled `<details>` with the heading inside its summary) is used by all of them, so the look is the same everywhere.
- A closed fold is easy to miss, so each summary shows what is inside and the chevron turns when open; the page can still be read start to finish by opening all of them.

## Not done

No change to the data, the table columns, the order buttons, the polling while a run is active, or the running and failed states. No "open all" button (can be added if wanted).

## Tests

Frontend only: lint, build, the browser tests (the ticket tests click Add buttons in the first kind of market, which stays open), one new browser test that opens a finished run and checks the "At a glance" box and that a fold can be opened. I measure the page height of the NBA run before and after, and look at desktop and phone screenshots.

## Checks to state at close

Lateral spread: the other long list on the same component family is the evidence list; it is folded here. The Prediction list and the Approval page are not affected. Causal depth: the page did not say what mattered; the summary says it first, and the folds keep the detail one click away instead of deleting it, so nothing a reviewer may need is lost.
