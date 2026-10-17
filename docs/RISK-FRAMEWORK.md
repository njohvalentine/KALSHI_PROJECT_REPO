# Risk-management framework for 100 US dollars in paper mode

**Status: a proposal for the client's approval.** Every number in the table in section 3 is marked "proposed". Nothing here has been applied: the limits in the app are still the old placeholders until the client gives his own numbers. Written 2026-10-17.

The client asked for this on 2026-10-16: "I will start with $100 and increase later, but for now, please keep the system in paper-trading mode and show me your proposed risk-management framework", and "I want the system to recommend NO BET whenever the research does not establish a sufficiently strong opportunity."

---

## 1. The starting point

- The bankroll is **100 US dollars, on paper**. Nothing real is ordered. The app has no trading code at all, and a test makes sure of it.
- **NO BET is the default answer** for every game. A game gets "Worth a look" only when a market passes all the tests, and even then it carries the caution "NO BET is the default" until the finished games show that our forecasts beat the Kalshi price.
- **A person approves every simulated order.** The system never approves one on its own.
- All limits are written in dollars, because dollars are easy to read and to check.

## 2. The rules, and why

**Small flat stakes, not a betting formula.** A well-known formula (the Kelly formula) says how much to bet when you know your edge. Our forecasts have not beaten the Kalshi price on the finished games (see the Dashboard), so we do not know that we have an edge, and the formula would say to bet nothing. Small, equal stakes limit what a wrong belief can cost, and they let the paper test run long enough to learn something.

**Bets on the same game are one risk.** A winner bet, a total bet and a margin bet on the same game move together: one surprise result can lose all of them. So the limit on a game counts all orders and all legs of that game together.

**Stop rules.** Two rules stop new orders after losses, because a long losing run is the best sign that a belief is wrong:
- *The day rule:* after the simulated results of the last 24 hours lose the limit, no new order is made until the oldest of those results is 24 hours old.
- *The total rule:* after the simulated results since the start (or since the last review date) lose the limit, no new order is made at all until the client and the operator have reviewed the results and set a new start date.

Both rules count only orders that have ended (settled). Wins offset losses. An order that is still open is counted by its cost in the stake limits, not by an unknown result.

## 3. The numbers (all proposed)

| Rule | Proposed value | Setting in the app | Where it is checked |
|---|---|---|---|
| Most one order may cost | 2 dollars | `ORDER_MAX_COST_USD` | Order checks (exists) |
| Most all orders of one game may cost together | 4 dollars | `ORDER_MAX_GAME_COST_USD` | Order checks (built, off until a value is set) |
| Most new orders approved in one day may cost | 10 dollars | `ORDER_MAX_DAY_COST_USD` | Order checks (exists) |
| Most orders open (not yet settled) at one time may cost | 20 dollars | `ORDER_MAX_OPEN_COST_USD` | Order checks (built, off until a value is set) |
| Stop for the day after a loss of | 10 dollars in 24 hours | `ORDER_PAUSE_DAY_LOSS_USD` | Order checks (built, off until a value is set) |
| Stop completely after a loss of | 20 dollars since the start | `ORDER_PAUSE_TOTAL_LOSS_USD` and `ORDER_LOSS_SINCE` | Order checks (built, off until a value is set) |
| Default answer | NO BET | none | Every page and alert (built) |
| A person approves every order | always | none | Approval screen (built) |

The existing placeholders are 5 dollars per order and 20 dollars per day. Against a bankroll of 100 dollars those are 5 and 20 percent, which is too much for a test whose point is to find out whether there is any edge.

## 4. The money arithmetic, said plainly

At 5 researched games a day, research costs about 0.43 dollars per game, so about **2.15 dollars a day, or about 65 dollars a month**. With new orders capped at 10 dollars a day, even a real edge of 10 cents for every dollar bet would earn about **1 dollar a day**. That is less than the research costs.

So for a bankroll of this size, the research costs are larger than any realistic profit. The paper test is therefore for learning whether an edge exists, not for earning back the research. If the test shows an edge, the bankroll and the stakes would have to grow before it pays for itself. If it shows none, the 65 dollars a month buys that answer, and nothing more.

## 5. What would have to be true before anything beyond paper (proposed)

The client wrote: "Please keep real-money trading disabled until we have sufficient evidence of a profitable strategy." This is our proposal for what "sufficient" means, for the client to change:

1. **At least 100 finished games** have been scored (today: 62).
2. **Our Brier score is better than Kalshi's by at least 0.005** on those games, and in the sport that would be traded (today: worse in every sport).
3. **At least 100 flagged bets** have ended, with an average simulated result above zero after fees, **and** the worst plausible value (not only the average) also above zero (today: 35 bets, average about -13 cents).
4. **The bookmaker comparison does not show the bookmakers ahead of us** on the same games.

Until then the answer stays NO BET and the system stays in paper mode. Real orders would also need a new Kalshi key, the client's own limits, and a separate decision (Milestone 7).

## 6. What the app enforces and what a person does

- **Enforced by the app:** the per-order and per-day cost limits, the 10-minute expiry, the price slippage limit, the checks before approval and placing, the stop rules once a value is set, the daily limit on researched games, and NO BET as the default answer.
- **Done by a person:** choosing the numbers, setting them in the settings file, reviewing the results after a stop, and deciding anything beyond paper.

## 7. Questions for the client

1. Which numbers do you want for each rule in section 3? The proposal is a starting point.
2. Is the proposed meaning of "sufficient evidence" in section 5 what you want, or do you want different thresholds?
3. After the total stop rule triggers, who decides when to start again, and on what basis?
