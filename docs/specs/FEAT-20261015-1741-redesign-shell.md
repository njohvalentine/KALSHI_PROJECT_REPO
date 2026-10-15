# Spec: redesign step 1, the shell

Branch `feature/sports-games-list` (base `master`). Step 1 of the redesign approved by the user on 2026-10-15 (sample: `docs/design/mockup-redesign-2026-10-15.html`). Items 2 to 6 are separate (see `TODO.md`). Frontend only: no backend change, no dependency.

## What is there now (read in the code)

- `app/(app)/layout.tsx`: a header (name, navigation, e-mail, Sign out), then a full-width orange bar "Paper trading: predictions are recorded and scored. No orders are sent to Kalshi.", then the page.
- `components/nav.tsx`: five links; the active one has a grey-blue background and normal text colour.
- `components/page-header.tsx`: 30 px title, description limited to 70 characters of width.
- The colour tokens in `globals.css` already match the sample (same background, card, primary, border, good and warn colours), so no new colours are needed.

## Design

- **Chip instead of bar:** the orange bar is removed. A small chip "Paper trading" (warn colours, rounded) goes in the header next to the e-mail, with the full sentence as its tooltip (`title`) and for screen readers. The sentence stays on the Approval page, where orders are prepared, so the warning remains visible where it matters (a short line at the top of that page).
- **Sticky header:** the header stays at the top while the page scrolls.
- **Navigation:** the active link gets the primary-soft background with primary-coloured text; others stay muted. Links stay the same five (the Dashboard tab comes with the Dashboard page in step 3, so that no link points to a page that does not exist).
- **Page title:** 28 px, with the sample's tight spacing; the description keeps its readable width.
- Nothing else on the pages changes in this step.

## Not done

No new tab, no page content changes, no table, no charts, no dark mode.

## Test

Rebuild the frontend image; new screenshots of the Games page (desktop and 390 px phone); `npm run lint`, `npm run build`, the browser tests. The tests find the navigation by its name "Main" and the Sign out button by role, which do not change; the Approval page line is checked in one added assertion.

## Checks to state at close

Lateral spread: every place that used the orange bar colours (`warn-soft` badges on Games, Opportunities, Evidence) keeps them, because those are badges, not the bar. Causal depth: the manager's complaint is the general look; this step fixes the frame every page shares, and the page-by-page look follows in steps 2 to 5.
