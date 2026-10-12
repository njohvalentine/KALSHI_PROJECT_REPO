# Spec: combination markets and 0% prices on the Markets page (BUG-20261012-1310)

Branch: `master` (base: `master`). Found by the user, who opened the Markets page against the live Kalshi API (VPN on) and saved it as a PDF.

## Verified cause

- The page shows entries like "yes Yosuke Watanuki,yes Kevin Krawietz / Tim Putz,yes Jiri Lehecka,..." with a price of 0%. These are **multivariate (combination) markets**: one contract that bundles many picks. Kalshi's Get Markets endpoint returns them unless told otherwise. Kalshi's docs (Get Markets, via search summary) list `mve_filter` with values `only` and `exclude`; the changelog says that when the parameter is omitted all markets come back. Our `GET /api/markets` never sent it.
- The 0% comes from our page: `percent()` turns the price string "0.0000" into "0%". Combination markets have no trades, so Kalshi reports a last price of zero, and we show that as if the market priced the outcome at 0%. A traded contract cannot have a last price of zero (the lowest price is 1 cent), so zero here means "no trade yet".
- Not found in the docs read: a category filter on Get Markets, so a sports-only list needs a different endpoint (events carry the category). That is not done here.

## Fix

1. `KalshiClient.list_markets` accepts `mve_filter`. `GET /api/markets` takes an optional `mve_filter` (`exclude` or `only`) and **defaults to `exclude`**, so the Markets page lists single markets. Any other value is rejected (422).
2. The Markets page shows "No trades yet" instead of "0%" when the last price is zero or missing.

## Not changed (recorded for later)

- Sports-only filtering (soccer, baseball, tennis) and ordering of the list; paging beyond the first 50; showing bid and ask. Each needs the events endpoint or more field checks, and the real response shape has not yet been seen by me (only through the user's PDF).
- The page was not re-tested against the live API from my environment, which cannot reach Kalshi; the user re-checks it.

## Lateral check

`list_historical_markets` and other Kalshi calls do not feed a user-facing list yet. Prediction and approval pages read our own database. No other place shows Kalshi prices.

## Tests

- The client passes `mve_filter` through, and drops it when not given.
- The endpoint sends `mve_filter=exclude` to Kalshi by default, passes `only` when asked, and answers 422 for other values.
- Web app: lint and build pass; a price of "0.0000", a missing price and a normal price render as "No trades yet", "No trades yet" and a percentage.
