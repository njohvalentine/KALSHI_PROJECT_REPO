# Spec: Milestone 5, approval screen with simulated orders (FEAT-20261013-1416)

Branch `feature/sports-games-list`. For approval; nothing here is built yet. **No order is ever sent to Kalshi in this milestone.** There is no trading code and no Kalshi key involved: everything is simulated, and the code for a real order is Milestone 7, after Kalshi's Developer Agreement has been read.

## Why, and what the client needs

The client wants a person to approve every bet. Milestone 5 builds the approval flow itself, so we can test it end to end, record what a bet at that moment would have paid, and let the client agree the limits, before anything real exists. The simulated orders also feed the paper results of Milestone 6.

## What Kalshi's order API looks like (read 2026-10-13 from docs.kalshi.com; to be re-read at Milestone 7)

- The current endpoint is `POST /portfolio/events/orders` (V2); the older `POST /portfolio/orders` was announced for deprecation no earlier than 6 May 2026.
- `side` is `bid` or `ask` and refers to the **YES leg only**: `bid` buys YES, `ask` sells YES. Buying NO is therefore a sale of YES. `count` and `price` are strings (fixed-point; price in dollars). `time_in_force` is required: `fill_or_kill`, `good_till_canceled` or `immediate_or_cancel`. `self_trade_prevention_type` is required. `expiration_time` (Unix seconds) goes with good-till-canceled.
- `client_order_id` is an optional free string; **the documentation does not say it is unique or that a retry with the same value is safe**. So protection against sending twice must be ours (below), and an order whose answer was lost must be looked up before anything is retried.
- The response gives `fill_count`, `remaining_count`, `average_fill_price` and `average_fee_paid` (per contract).
Because the API is moving, this milestone stores an order in our own terms (market, side yes or no, price in dollars, contracts, expiry) and maps to Kalshi's fields only in Milestone 7.

## The flow

1. **Prepare.** On the Opportunities page (and a run page) a market shows **Prepare order**. The person enters the number of contracts (default 1) and presses it. The system reads the current price and creates an order in state `proposed` with: the market, the side (yes or no) and the executable ask at that moment, the contracts, the maximum cost (price times contracts plus the estimated fee), our probability, the gap after fees, the forecast's age, a unique `client_order_id`, and an **expiry** (`ORDER_EXPIRY_MINUTES`, default 10). Only one open order per market.
2. **Checks shown on the Approval page**, each with a plain result: game not started; forecast not older than `OPPORTUNITY_MAX_AGE_HOURS`; the order is within the limits; the price has moved by at most `ORDER_MAX_SLIPPAGE_CENTS` (default 2) against us since it was prepared (read again at that moment); enough contracts offered at that price. A failed check does not remove the order; it blocks approving it and says why.
3. **Approve or reject.** Approve records who and when and moves the order to `approved`; Reject (with an optional reason) ends it. An order not approved by its expiry becomes `expired` and cannot be approved. All of this is by explicit button presses on the Approval page; nothing is approved automatically, by the watcher or by anything else.
4. **Place (simulated), a separate step after approval.** It reads the price once more, re-checks the same rules and the limits, and records a **simulated fill**: filled contracts (at most the contracts offered at the best ask), the price and the estimated fee, or `simulated_rejected` with the reason if the price moved too far. The move from `approved` to `placed` is a single atomic database update that only one caller can win, so a double click or a retry can never place an order twice. **No call to Kalshi's order endpoints exists in the code.**
5. **Outcome.** When the game ends (`resolve-records` already looks up the results) the simulated order is settled: win pays 1 dollar per contract, minus the price and the fee; a loss loses the price and the fee. The Results page shows the orders and the paper result.
6. Every state change is written to an append-only history (`order_events`: time, from, to, who, reason). Nothing about an order is edited in place except its state and fill fields.

## Limits (settings; the betting limits the client has to agree before any real order; defaults are placeholders)

`ORDER_MAX_CONTRACTS` (default 10), `ORDER_MAX_COST_USD` per order (5.00), `ORDER_MAX_DAY_COST_USD` for all orders approved in a UTC day (20.00), `ORDER_EXPIRY_MINUTES` (10), `ORDER_MAX_SLIPPAGE_CENTS` (2). A limit is checked at preparing, approving and placing. **Questions for the client (he decides, not us):** the most he wants to risk on one bet, and in one day.

## Pages

- **Approval:** "Waiting for approval" (cards: the exact order in words, the checks, a countdown to expiry, Approve and Reject), then "Recent orders" with their state.
- **Opportunities / run page:** Prepare order with the contracts box; the cost note says that it is simulated.
- **Results:** a list of simulated orders (market, side, price, contracts, state, result when the game ended, paper result) with totals, plus a link to the scores of the forecasts. A banner on these pages says no order is sent to Kalshi.

## Data

`orders` (id, client_order_id unique, run_id, event_ticker, market_ticker, outcome label, side, price, contracts, max_cost, fee_estimate, our_probability, gap, forecast_at, state, created_at, expires_at, approved_by, approved_at, rejected_reason, placed_at, fill_contracts, fill_price, fill_fee, reject_detail, settled_at, won, paper_result), `order_events` (append-only). States: `proposed`, `approved`, `rejected`, `expired`, `placed`, `simulated_rejected`, `settled`.

## Security

All order endpoints need sign-in and the same request header guard as starting a run; the approver is the signed-in user, stored with the time; a state change that is not allowed from the current state is refused; the order's price and contracts cannot be changed after preparing (to change them, prepare again).

## Tests (fakes only)

Prepare reads the price and computes the exact order; one open order per market; each check passes and fails on its own with its plain reason; limits at prepare, approve and place; expiry; approve and reject; place twice (and two parallel places) fills once; a price move beyond the slippage limit gives a simulated rejection with the reason; fills are capped at the contracts offered; settlement for a win and a loss with the fee; the history records every change; endpoints need login and the header; no Kalshi order call exists (a test asserts the client class has no method that posts to a trading path).

## Not in this milestone

A real order, Kalshi's request and response mapping, the Kalshi key, demo or production trading, selling a position, partial fill handling beyond the best ask.

## Decisions for you

1. Approve this design?
2. The limits are placeholders; do you want to ask the client for his maximum per bet and per day now, or after Milestone 5 is built?


## Result (2026-10-13; design approved by the user with placeholder limits)

Built as specified: tables `orders` and `order_events` (migration `89690e74334f`; a partial unique index allows one open order per market), `app/orders.py` (prepare, checks, approve, reject, place, expire, settle, endpoints), settings `ORDER_*`, `resolve-records` also settles simulated orders, the Approval page, Prepare order on the Opportunities page and on flagged rows of a run page, the Orders section of the Results page. 461 backend tests pass; checked live against a real forecast: an order was prepared, approved and placed (3 contracts "no" on Over 9.5 runs at 76 cents, fee 0.02, the MLB fee multiplier of 0.5 applied), a second placing was refused, a second order for the same market was refused while one was open. No Kalshi trading code exists: a test fails if any source file makes an outgoing POST or names Kalshi's order endpoints, or if the Kalshi client gains a method that sounds like trading.

**Differences from the design, and why:** a placed order is never partially filled in this version (a check requires enough contracts at the price and otherwise the simulation refuses it), so "fill capped at the contracts offered" does not occur; "Prepare order" is offered for flagged rows only in the pages, although the endpoint accepts any market with a price (the checks show whether it is still worth a look); the day limit counts approved orders at their maximum cost until they are placed, then at what they cost.

**Placeholder limits** (`ORDER_MAX_CONTRACTS` 10, `ORDER_MAX_COST_USD` 5.00, `ORDER_MAX_DAY_COST_USD` 20.00, `ORDER_EXPIRY_MINUTES` 10, `ORDER_MAX_SLIPPAGE_CENTS` 2) stand until the client answers; the question was drafted for him.
