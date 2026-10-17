# Spec: bets on the same game count as one risk (client priority F)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "Make sure correlated bets are identified and properly accounted for in risk calculations." Approved by the user on 2026-10-17 as the eighth item; `docs/RISK-FRAMEWORK.md` (item G) proposes the numbers.

## What is there now (read in `orders.py`, `runs.py`, the models)

- A ticket may hold several markets of one game and the page marks them "rough" (they move together), but the limits ignore it: `ORDER_MAX_COST_USD` is per order, `ORDER_MAX_DAY_COST_USD` is per day, and nothing adds up what is at risk on one game across orders, or what is open at one time. Three separate orders on one match (the winner, the total, the margin) can each pass every check and together put several times the intended amount on one result.
- Each order has legs (`order_legs`), and each leg has the run it came from; the run knows the game (`runs.event_ticker`, the winner event). A market of a companion event (total, spread) belongs to the same game through its run, even though its own event ticker differs; `order_legs.event_ticker` is the market's group, so it cannot be used to find the game.

## Design

- **The game of a leg is the game of its run** (`runs.event_ticker`). All markets researched in one run (winner, total, both teams to score, margin) are the same game, and so are two runs of the same game.
- **Open exposure:** the cost of an order that is approved (its maximum cost) or placed (what it cost), until it is settled, rejected or expired. A ticket's cost counts **in full against every game it touches** (the conservative reading: if one leg fails the whole ticket is lost).
- **Two new limits, both off at `0` until the client approves a value** (same reason as the stop rules): `ORDER_MAX_GAME_COST_USD` (the most open orders of one game may cost together, this one included; proposed 4) and `ORDER_MAX_OPEN_COST_USD` (the most all open orders may cost together; proposed 20).
- **Two new blocking checks** in the common list, `within_game_limit` (one line per game of the order: "Roma vs Lazio: $3.10 on this game together (limit $4.00)") and `within_open_limit`, applied when an order is prepared (refused with the same sentence), approved and placed, like the other checks. A proposed order counts only once it is approved; the order being checked is not counted twice.
- The Approval page shows them with plain labels. `docs/RISK-FRAMEWORK.md` already lists them as "to be built" and is updated; the test that compares its numbers with `.env.example` covers the two new settings.

## Not done

No change to the existing limits' values; no calculation of a combined probability of loss (the cost counts in full, which needs no assumption about how strongly the bets move together); no limit by league or by sport; a game's exposure ends when its orders are settled (no carry-over of losses, which is the stop rules' job).

## Tests

Backend: the games of an order (a single order, a ticket of two games, a companion market through its run); open exposure by state (approved at maximum cost, placed at fill cost, settled/rejected/expired not counted); the game limit at and just above the limit across orders of different markets of one game; a ticket counted in full against each of its games; the open limit; both limits off at 0; preparing refused with the sentence; approving blocked; placing rejected with the check named; bad values refused; the document's numbers agree with `.env.example`. Frontend: lint, build, browser tests.

## Checks to state at close

Lateral spread: every path that makes an order live goes through the common check list (prepare, approve, place), and I confirm each refuses; I search for any other writer of order state. Causal depth: the request is about correlation; counting every leg of a game, in every order, as one cost removes the need to guess correlations, and the cases (companion markets, re-researched games, tickets) are each covered by a test.
