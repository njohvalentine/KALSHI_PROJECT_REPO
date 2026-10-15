# Spec: redesign step 2, the Opportunities page as a table

Branch `feature/sports-games-list` (base `master`). Step 2 of the redesign approved on 2026-10-15 (sample: `docs/design/mockup-redesign-2026-10-15.html`). Frontend only: no backend change, no dependency (the shadcn `components/ui/table.tsx` already exists).

## What is there now (read in `app/(app)/opportunities/page.tsx`)

Each researched game is a card (`<li>`): title link, start time, badges (Worth a look or Not flagged, Sport not yet measured, Forecast is old), the buy sentence, four small figures (our probability / market, gap, range of the forecasts, supported claims), the Add-to-ticket button and a link to the game, an "N more markets are also worth a look. See all" line, the risks line, the forecast age and the Research-again button. Below the list: the filter links, the explanation, and the "Recent alerts" section (not part of this step).

## Design

- The list becomes one table in a bordered card, one row per game, same data and same order:
  - **Game:** title (link to the game), start time, and "forecast N h ago" in small text.
  - **Bet:** the same buy sentence as today; below it, in small text, the "N more markets of this game are also worth a look. See all" line and the risks line ("Take care: ..." or "Why not: ...") when they exist.
  - **Our / market:** "65% / 50%", with the range of the forecasts in small text under it ("range 3 points"), so no figure of the old card is dropped.
  - **Gap after fees:** the one bold figure, green for a flagged row, plain for an unflagged one.
  - **Claims:** the supported-claims number.
  - **Status:** the same badges as today.
  - **Actions:** Add to ticket (same component and props) on a row with a fresh forecast; on an old forecast the text "research the game again to add it to a ticket" stays and Research again is the main button; otherwise Research again stays as the quieter button next to Add to ticket.
- A row without a price ("unavailable" or no best market) shows its reason across the Bet, Our/market and Gap cells, as today's card does.
- Old forecasts keep the greyed look. The table scrolls sideways on a phone instead of squeezing (the first column stays readable).
- The filter links, the count sentence, the empty-state alerts, the closing "not a recommendation" paragraph and the Recent alerts section are unchanged.
- The two browser tests that find a row by `li` are changed to find it by table row (`tr`); their meaning does not change.

## Not done

No sorting or search controls, no change to how rows are chosen or ordered, no change to the alerts section, no backend change.

## Test

Rebuild the frontend image, screenshots of the page on desktop and phone (all researched games), `npm run lint`, `npm run build` and the browser tests (the two Opportunities tests run only when a matching row exists; if none exists they skip with a reason, so I will also check by eye that Add to ticket works on a real row).

## Checks to state at close

Lateral spread: the Games page and the Approval page also show lists that could become tables; that is step 5, not changed here. Causal depth: the complaint is that the page looks like a pile of identical cards; the table makes the one deciding figure stand out and puts all games in one scannable view, with no information removed.
