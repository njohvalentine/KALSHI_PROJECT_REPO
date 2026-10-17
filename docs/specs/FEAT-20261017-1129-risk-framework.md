# Spec: a risk-management framework for 100 US dollars in paper mode (client priority G)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "Regarding my total trading budget, I will start with $100 and increase later but For now, please keep the system in paper-trading mode and show me your proposed risk-management framework." Approved by the user on 2026-10-17 as the seventh item.

## What is there now (read in `orders.py`, `config.py`)

- Limits on a simulated order: `ORDER_MAX_CONTRACTS` 10, `ORDER_MAX_COST_USD` 5, `ORDER_MAX_DAY_COST_USD` 20 (what the orders approved today may cost in all), a 10-minute expiry, and at most 2 cents of price slippage. All are placeholders. Nothing limits the loss: there is no rule that stops new orders after losses, and nothing counts bets on the same game together (that is item F).
- The values (5 and 20) are large against a bankroll of 100 (5 and 20 percent).

## Design

**1. A document, `docs/RISK-FRAMEWORK.md`, in plain English, written for the client.** It states, as a proposal for his approval (every number marked "proposed"):
- **The starting point:** a paper bankroll of 100 dollars; nothing real is ordered; NO BET is the default answer (item H); a person approves every order.
- **Stake rules (proposed):** at most 2 dollars on one order; at most 4 dollars on one game, counting all orders and all legs of that game together because they move together (the rule itself is item F); at most 10 dollars of new orders in a day; at most 20 dollars of orders open (not yet settled) at one time.
- **Stop rules (proposed):** no new order for the rest of the day after the simulated results of the last 24 hours lose 10 dollars or more; no new order at all after the simulated results since the start (or since the last review date) lose 20 dollars or more, until the client and the operator review and set a new start date.
- **Why flat small stakes and no "Kelly" formula:** that formula needs a proven edge. Our forecasts have not beaten the Kalshi price (Dashboard), so the formula would say to bet nothing. Small flat stakes limit what a wrong belief can cost.
- **The money arithmetic, said plainly:** at 5 researched games a day the research costs about 2.15 dollars a day (about 65 a month). With stakes capped at 10 dollars a day, even a real edge of 10 cents per dollar would earn about 1 dollar a day. For a bankroll this small, research costs are larger than any realistic profit; the paper test is for learning whether an edge exists, not for earning back the research.
- **Evidence needed before anything beyond paper (proposed, for the client to change):** at least 100 finished games; our Brier score better than Kalshi's by at least 0.005 on them, and in the sport to be traded; at least 100 flagged bets whose average simulated result is above zero after fees (not just on average: the worst plausible value must also be above zero); the bookmaker comparison not showing the bookmakers ahead of us. Until then the answer stays NO BET.
- **What the app enforces and what stays a person's job:** a table of each rule against where it is checked (the order checks, a setting, or by hand).
- **Questions for the client:** his own numbers for each proposed value, and whether the evidence criteria are the ones he wants.

**2. Two new stop-rule settings and one check in the app** (the stop rules above are the only rules not yet enforced):
- `ORDER_PAUSE_DAY_LOSS_USD` and `ORDER_PAUSE_TOTAL_LOSS_USD`, with `0` meaning off, and `ORDER_LOSS_SINCE` (a date, empty = from the first order). The default is off until the client approves a value (a stop rule with an invented value would stop a test for no agreed reason); the document and `.env.example` give the proposed values.
- A blocking order check `not_paused`, shown on the Approval page with its detail ("the simulated results of the last 24 hours are -$X.XX (limit $Y)"), applied when an order is prepared (refused with the same sentence), approved and placed. The loss is the sum of `paper_result` of the settled orders (the last 24 hours by settlement time, or since `ORDER_LOSS_SINCE`).
- The existing limits are **not** changed here: their values change only when the client approves values (then it is a line in `.env`).

## Not done

No change to the existing limit values, no per-game limit and no open-exposure limit (item F, which uses the same check list), no change to how the paper result is calculated, no bankroll setting that derives the limits (the limits stay dollar amounts, which is easier to read and check).

## Tests

Backend: the stop check with 0 (off); a day loss at and below the limit; a total loss; `ORDER_LOSS_SINCE` ignores older orders; wins offset losses; preparing is refused with the sentence; approving and placing are blocked; the check shows on the Approval page data; a bad setting is refused with a clear message. Document: a test that checks every number in the document's table of proposed values against `.env.example`'s comments, so the two cannot disagree.

## Checks to state at close

Lateral spread: the check goes where the other blocking checks go (prepare, approve, place), and I confirm each of the three refuses. Causal depth: the request has three parts (limits for $100, when to pause, NO BET by default); limits and the default exist, the pause rule did not, and the money arithmetic is added because it changes what the framework is for.
