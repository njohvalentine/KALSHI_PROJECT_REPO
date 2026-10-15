# Spec: "Add to ticket" on every researched game of the Opportunities page (FEAT-20261015-0918)

Branch `feature/sports-games-list` (base `master`). For approval; nothing is changed yet. The synthesis was approved by the user on 2026-10-15.

## Why (the need behind the request)

The client builds a ticket from the ranked list of games and said, when asked whether he adds only the games marked worth a look or any game: "it can be any depending on each situation". He decides; the system should not hide a game from the ticket because our rule did not flag it. Today the Opportunities page offers the add button only on flagged rows, and only one on each (the best market and side). On a run page every priced market has a "yes" and a "no" button, but a person building a ticket from the ranking has to open each game.

## Verified in the code

- `frontend/app/(app)/opportunities/page.tsx` (row component): `AddToTicket` is rendered only when `o.flagged && !o.stale`. A row with a price but no flag shows the numbers and the reasons and no button. The page's "All researched games" view lists those rows.
- The backend already accepts any market of any researched game in a ticket: it requires a fresh forecast (at most `OPPORTUNITY_MAX_AGE_HOURS`, 12) and a game that has not started, nothing about the flag; the Approval page shows "still worth a look" as an informational check, not blocking.
- `TicketLeg` (`frontend/components/ticket.tsx`) has no notion of whether the leg was flagged; the run page buttons (`prediction-table.tsx`) offer both sides of every priced market.

## Design

1. **The button on every priced, fresh row.** A row that has a best market and a price and whose forecast is not old gets the same `AddToTicket` button: the best market and side by gap, as shown in the row. A row whose forecast is old (stale) shows, in place of the button, "The forecast is old: research the game again to add it", because the server would refuse it anyway. A row with no price shows nothing new.
2. **A link to the other markets.** Every row with a button also shows "Other markets and the other side: open the game" linking to the run page, where every market has "yes" and "no" buttons (already built).
3. **A plain note on the ticket.** Each leg carries `flagged` (true when our rule marks that market and side worth a look: on the Opportunities page, the row's flag; on a run page, `meaningful` and the side equals the flagged side). The ticket panel shows, when at least one leg is not flagged: "N of these legs are not marked worth a look: our estimate there is not better than the market's price." Legs saved earlier in the browser without the field are not counted. The panel's other texts are unchanged.
4. **No backend change and no new setting.**

## Not changed

The ranking order, the flag rule, the default "Worth a look only" view (the unflagged rows appear in "All researched games" as today), the checks of the Approval page, the ticket limits.

## Tests

Playwright (the tests added on 2026-10-14): on the "All researched games" view, every row with a fresh forecast and a price has an add button, and adding a row that is not flagged shows the note "not marked worth a look" on the ticket panel; a stale row shows the research-again text. These tests skip themselves with the reason when no fresh forecast exists (forecasts older than 12 hours are the common case overnight). Frontend lint and build.

## Checks to state at close

Lateral spread: every place that renders an add button (Opportunities row, run page markets) carries `flagged`, and the panel is the only reader. Causal depth: the need is "let me choose any game"; the button on the ranking answers it, the link to the run page answers "choose another market or side", and the note keeps the "not flagged" signal visible instead of hiding the game.

## Result (2026-10-15)

Built as specified, frontend only: every Opportunities row with a price and a fresh forecast has the add button (best market and side) and a link "Other markets and the other side: open the game"; a row with an old forecast says to research the game again; each leg carries `flagged` (the row's flag on the Opportunities page; `meaningful` and the same side on a run page) and the ticket panel says "N of these legs are not marked worth a look: our estimate there is not better than the market's price." Lint and build clean; the frontend image was rebuilt (the `npm ci` that stalled on 2026-10-14 finished this time).

Browser tests: 2 new (a non-flagged row can be added and the ticket shows the note; a row with an old forecast has the text and no button). Run live on 2026-10-15: with every forecast older than 12 hours the first skipped itself (as designed) and the second passed; after researching one upcoming game (Zverev vs de Minaur, about 0.45 USD) the first one ran and passed too. Total: 9 browser tests, 8 pass and 1 (a prepared ticket on the Approval page) skips itself when no game is open for a ticket.

Checks done: lateral spread (the two places that render an add button, the Opportunities row and the run page markets, both carry `flagged`; the panel is the only reader; legs saved earlier without the field are not counted); causal depth (the button answers "let me choose any game", the link answers "another market or side", the note keeps the not-flagged signal visible).
