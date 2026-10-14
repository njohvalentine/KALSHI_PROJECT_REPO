# Spec: ticket wording and slow reads (ISS-20261014-1026, ISS-20261014-1027)

Branch `feature/sports-games-list` (base `master`). For approval; nothing here is built yet. Found by driving the new ticket screens in a real browser on 2026-10-14 (screenshots in `docs/design/screenshots-2026-10-14/`).

## What is wrong (verified in the code and the browser)

1. **Wording.** `frontend/app/(app)/approval/page.tsx` `orderSentence` says "ticket of N games" and the checks are prefixed "Game N:" where N is the leg's position. A leg is one market; a game can have several legs (since FEAT-20261014-0910), so "Game 4" can be the second leg of game 3.
2. **Slow reads.** `prepare_ticket` and `_checked` in `backend/app/orders.py` call `fresh_market` for each leg one after the other with a cache per run. The cache saves repeats of one game but the different games are still read one at a time (each read asks Kalshi for the winner event, the companion events and the fee). The browser measured 10 to 20 seconds for 3 games; 17 legs from about 10 games would take about a minute, in prepare, on every load of the Approval page, in approve and in place.

## Fix

1. Say "leg" everywhere a leg is meant: "Buy 1 ticket of 4 legs", and checks labelled "Leg N". The ticket's title already says "4 legs in 3 games".
2. A helper `fresh_markets(app, pairs)` reads each distinct run once, all at the same time (`asyncio.gather` over the distinct run ids, filling the same cache), and then picks each leg's market. `prepare_ticket` and `_checked` use it. The concurrency is bounded by the number of distinct games on a ticket (at most 20); the Kalshi client is already used concurrently by the Opportunities page (`collect`, with a semaphore of `SPORTS_FETCH_CONCURRENCY`, 6), so the helper uses the same limit.

## Not changed

The order of a replaced leg in the ticket panel (it moves to the end), cosmetic. The hidden duplicate "Add" buttons of the run page (the table and the phone list both render them; one is hidden by the screen size), by design.

## Tests

A test with a fake Kalshi that counts concurrent calls: a 4-game ticket reads the games at the same time and each game once. Existing ticket tests still pass. Web app: lint, build and a look at the Approval page.

## Checks to state at close

Lateral spread: every caller of `fresh_market` (prepare, checks, approve, place, the Approval page via `order_with_checks`), and the other places that say "game" for a leg (Results page, ticket panel). Causal depth: the slowness has two parts (sequential games, repeated reads per page load); the second is not changed here: an Approval page load still reads prices once, which is wanted because the checks must show today's prices.

## Result (2026-10-14)

Built as specified. Wording says "leg" on the Approval page (sentence and check labels), the Results page and the ticket panel. `fresh_markets` in `backend/app/orders.py` reads each distinct game once and the games at the same time (limit `SPORTS_FETCH_CONCURRENCY`); prepare and the checks use it. A new test fails on the old code (reads one after the other) and passes now. 490 backend tests pass; lint and build are clean. Measured live: reading 6 games for a ticket took 4.3 s (the 3-game ticket took 10 to 20 s before); that ticket was then refused for a combined price below one cent, which is the intended message.

Checks done: lateral spread (callers of `fresh_market`: prepare, the checks used by the Approval page, approve and place all go through `_checked`; the other uses of the word "game" for a leg: Approval, Results, ticket panel); causal depth (the repeated read on every page load stays, by design: the checks must show today's prices).
