# Spec: a centered sign-in page

Branch `feature/sports-games-list` (base `master`). The user asked on 2026-10-15 to start the UI improvement with the login page, because the manager said the UI "looks weird". First step only; the rest of the redesign is not part of this item.

## What is wrong (checked on screenshots of the running app, desktop 1440x900 and phone 390x800)

`frontend/app/login/page.tsx` puts the title, the text and the form in the same left-aligned content column as the other pages, with a 24rem-wide form. On a wide screen the form is stuck at the left edge and the rest of the page is empty. The app name is only small header text, the page does not say what the app is, and the line "Use the account the operator created for you." reads as an internal note. Styles, fonts and requests are fine (no failed requests).

## Design

- Only `frontend/app/login/page.tsx` changes (and `login-form.tsx` only if a class needs to change). No new dependency, no new file, no backend change. The form code, the requests and the error messages stay exactly as they are.
- The header bar is removed on this page. The page is one vertically and horizontally centered column on the same background colour: the app name "Forecast desk" in larger bold text, one line under it ("AI research for Kalshi sports markets"), a white card (same border, radius and background tokens the other pages use) holding "Sign in", the hint "Use the account your administrator gave you." and the existing form, and below the card the small line "Paper trading only: nothing is ordered on Kalshi."
- Card width about 24rem, full width minus the gutter on a phone; same colours and font as the rest of the app (no new colours).
- A card from `npx shadcn add card` is not added: the card is a plain bordered box with the existing tokens, so no new component file is needed.
- The browser tests that sign in use labels and roles (`Email`, `Password`, `Sign in`), which stay.

## Not done

The other pages, the dashboard, tables, charts and dark mode.

## Test

Rebuild the frontend image, take new desktop and phone screenshots of `/login` (before shots exist: `deployed-login.png`), run `npm run lint`, `npm run build` and the 10 Playwright tests against the rebuilt stack.

## Checks to state at close

Lateral spread: the only other page outside the signed-in layout is none (the 404 and error pages are checked for the same left-stuck look). Causal depth: the need is "a manager's first sight looks finished"; the centered layout fixes the layout, the identity line and the wording, not only the position.
