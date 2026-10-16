# Spec: redesign step 5, one table header style and the Approval recent orders as a table

Branch `feature/sports-games-list` (base `master`). Step 5 of the redesign, as split with the user on 2026-10-16 (the run page is its own item, step 5b). Sample: `docs/design/mockup-redesign-2026-10-15.html`. Frontend only.

## What is there now (read in the code and on screenshots)

- Games, Prediction, Opportunities and Results already show their lists as a table inside a bordered card. The table header cells are set in one place, `components/ui/table.tsx` (`TableHead`: 14 px, medium weight, full-strength text colour), so they look like body text; the sample uses small, grey, upper-case headers.
- `TableHead` is also used by the tables on the run page (`prediction-table.tsx` and the evidence parts), so a change there reaches them as well.
- Approval: "Waiting" orders are cards with the checks and the Approve and Reject buttons. "Recent orders" is a stack of plain cards (state badge, time, the order sentence, the reason).

## Design

- **One header style, set once:** `TableHead` becomes 12 px (`text-xs`), semi-bold, upper-case with a little letter spacing, in the muted text colour. No page file changes for this. Because upper-case letters are wider, the tightest table (Opportunities at 1280 px, which fitted with about 10 px to spare) is measured again after the change; if it overflows, the headers of that table are shortened, not the data.
- **Approval, Recent orders as a table** in a bordered card, with the columns When (the created time), Order (the same sentence as today), Status (the same badge) and Why (the reason, when there is one). Nothing from the cards is dropped. "Waiting" stays as cards, because each carries its checks and its two buttons. The empty text "None yet." stays.
- The browser test that rejects a ticket counts `li.rounded-xl` in the Waiting section, which does not change.

## Not done

No change to Waiting cards, the run page (step 5b), filters, sorting, or any data.

## Tests

Lint, build, the browser tests, desktop and phone screenshots of Games, Prediction, Opportunities, Results and Approval, and a measurement that none of the five pages scrolls sideways at 1280 px (except the Opportunities and Results tables, which may scroll inside their card on a phone, as before).

## Checks to state at close

Lateral spread: every table that uses `TableHead` gets the new style; the run page's tables are included on purpose and checked by eye (their layout otherwise stays for step 5b). Causal depth: the tables looked like plain text grids because the header looked like body text; one shared style fixes that for every page now and for every table added later.
