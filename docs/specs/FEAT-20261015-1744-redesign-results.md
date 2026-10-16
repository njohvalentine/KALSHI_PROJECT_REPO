# Spec: redesign step 4, the Results page

Branch `feature/sports-games-list` (base `master`). Step 4 of the redesign approved on 2026-10-15 (sample: `docs/design/mockup-redesign-2026-10-15.html`, Results tab).

## What is there now (read in `app/(app)/results/page.tsx`)

A long description that sends the reader to a command line ("printed by the command score-records (see the run guide)"), one grey sentence with the totals, then each simulated order as a small card: badges (state, Won or Lost), "placed" time, an Open link, the legs of a ticket as a list, and one sentence with contracts, price, fee and paper result. The scores of the forecasts are not on the page.

## Design

- **Description** in plain words, no command: "Simulated orders and what they would have paid once the game ended. Nothing was sent to Kalshi. How the forecasts compare with the Kalshi price is on the Dashboard." (the last words link to the Dashboard).
- **Three summary cards** (same card style as the Dashboard): *Simulated orders settled* (count, how many won, paper result in dollars); *Chosen side at the ask* (the average result per contract and the number of bets, over all scored outcomes: what buying the side we rated higher at the ask price would have paid); *Flagged bets* (won out of bets and average result, with "too few to read" under 30). The last two come from `/api/dashboard`, which gets one new field `chosen_side` (bets, won, average result, taken from `score_records["paper_all"]`, already computed there). If the Dashboard call fails the page still shows the orders and the first card, with a short note.
- **The orders become a table** in a bordered card: Placed, Game (title, and "Ticket of N legs" when it is one), Bet (the side and outcome; a ticket lists its legs under the first line with won or lost), Price, Fee, Paper result (green for plus, red for minus, "known when the game ends" while open), a status badge (Placed, Settled, and Won or Lost or Returned) and an Open link. The same data as today: nothing is dropped.
- The empty state and the "a handful of orders says almost nothing" caution stay.
- The browser test "the Results page loads" also checks that the three card labels are shown.

## Not done

No filters, no charts, no per-sport profit table, no change to how orders are settled.

## Tests

Backend: one added assertion in `tests/test_dashboard.py` (`chosen_side` equals `score_records` `paper_all`). Frontend: lint, build, browser tests, desktop and phone screenshots (with the one existing settled order).

## Checks to state at close

Lateral spread: the Approval page lists open and recent orders as cards; that is step 5. Causal depth: the page was about simulated orders only while the more telling numbers (the chosen side over all scored outcomes, the flagged bets) were nowhere in the app; the cards bring them to the page where a person looks for results, with the same too-few cautions as the Dashboard.
