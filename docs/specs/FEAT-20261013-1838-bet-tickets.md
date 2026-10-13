# Spec: bet tickets of several games, combos (FEAT-20261013-1838)

Branch `feature/sports-games-list`. For approval; nothing here is built yet. Requested by the client on 2026-10-13: "Each game is not placed as stand alone. We usually create a combo which is a combination of games on one bet. So after analysis and rankings of best possible games ... we should be able to select more than one game on a bet ticket before approval."

## What a ticket is

One bet made of several **legs** (each leg: one market of one game, bought on its "yes" or "no" side). The ticket wins only if **every** leg wins. The person picks the legs from the ranked list, sees the whole ticket, and approves or rejects the ticket as one. A ticket with one leg is today's single order; there is one code path for both.

## What Kalshi offers for combos (read 2026-10-13, docs.kalshi.com; to be read again at Milestone 7)

Combos are "multivariate event collections". A combo market is discovered through the collections endpoints and priced through the **RFQ flow**: the requester asks, market makers answer with quotes for the full amount, the requester accepts one, the maker confirms; combos are high volatility markets (3-second confirmation window, 1-second execution timer). The documents I read do not say whether legs can come from different games or sports, how the payout is defined, or any combo-specific fee. Earlier we saw combo markets in the market list with no trades and zero prices, so **there is no public combo price to read**. A real combo order therefore needs the authenticated RFQ flow: Milestone 7, after the Developer Agreement is read. This spec covers the **simulated** ticket only.

## How a ticket is priced and judged (simulation)

- **Combined probability** = the product of the legs' probabilities (for the side bought). This assumes the games are independent, which is reasonable for different games and wrong for several markets of one game (they are strongly linked: a high-scoring game moves the total, both teams to score and the margin together). **A ticket may therefore hold at most one leg per game** (a plain message says why).
- **Combined price** = the product of the legs' executable prices (a fair combo price). Kalshi's real combo quote comes from market makers and includes their margin, so the simulated price is **cheaper than the real one and simulated results are optimistic**. The page says so wherever these numbers appear.
- **Fee:** the series' published formula applied to the combined price (a stated assumption; the real combo fee is not documented in what I read).
- **Combined gap** = combined probability minus combined price minus fee per contract. A ticket also shows "this ticket wins about N percent of the time" (the combined probability) because several modest legs make an unlikely ticket.
- **Errors multiply.** If each leg's probability is a little too high, the combined probability is too high by more. The page shows a short plain-words warning when a ticket has three or more legs; legs are limited by `TICKET_MAX_LEGS` (default **4**, a placeholder for the client).

## The flow (as Milestone 5, with legs)

1. **Pick legs.** On the Opportunities page each game row has **Add to ticket** (the best market of the game, or "choose another market" later). A ticket panel on the page lists the chosen legs with the combined probability, price, gap and warnings; the person sets the number of contracts and presses **Prepare ticket**. (A run page keeps a single-leg **Prepare order**, which creates a one-leg ticket.)
2. **Prepare** reads today's prices for every leg and creates the ticket in state `proposed` with the same expiry and limits as an order; the limits (`ORDER_MAX_CONTRACTS`, `ORDER_MAX_COST_USD`, `ORDER_MAX_DAY_COST_USD`) apply to the **ticket** (cost = combined price times contracts plus fee).
3. **Approval page** shows every leg in words, the combined numbers, and the checks: ticket-level (not expired, within the limits, at most `TICKET_MAX_LEGS` legs, one leg per game) and **for each leg** (game not started, forecast recent, price has not moved against us, enough contracts offered, still worth a look as information). A failed blocking check on any leg blocks the ticket.
4. **Approve / Reject / Place in the simulation** as now (one atomic step each; placing twice is impossible). Placing re-reads every leg's price; the simulated fill is at the product of the prices of that moment.
5. **Settlement:** the ticket is won only if every leg has won, lost as soon as any leg has lost (it is settled when its last leg is known or when one leg has lost); if a leg is voided the ticket is settled with the stake returned and the reason shown (real combos reduce the legs; simulating that is not worth the complexity).

## Data

`orders` stays the ticket (its price is the combined price, its probability the combined probability, its market ticker the first leg's). New table `order_legs` (id, order_id, position, run_id, event_ticker, market_ticker, outcome, title, game_start, side, price, our_probability, forecast_at, open, fill_price, won). Existing single orders are migrated to one leg each. "One open ticket per market" moves to the legs: a partial unique index on `order_legs.market_ticker` where `open`, kept in step with the ticket's state in the same update. `order_events` is unchanged.

## API

`POST /api/orders` takes `{"contracts": n, "legs": [{"run_id": ..., "market_ticker": ...}, ...]}` (the single-market body is replaced); the other endpoints keep their paths and return the ticket with its legs and checks.

## Pages

Opportunities: a checkbox or button per row, the ticket panel, a note that simulated combo prices are optimistic. Approval and Results: tickets with their legs listed. The run guide and the documents get a short ticket section.

## Tests (fakes only)

Combined probability, price, fee and gap on a hand-worked three-leg ticket; one leg per game refused; more than `TICKET_MAX_LEGS` refused; limits on the ticket's cost; every per-leg check failing alone blocks the ticket and names the leg; one open ticket per market across tickets; placing twice and in parallel fills once; settlement for all legs won, one leg lost (settled at once), a voided leg, and legs resolving at different times; the migration turns existing orders into one-leg tickets; the single-leg flow still works; no Kalshi order call exists (the existing guard test stays).

## Not in this spec

A real Kalshi combo (collections lookup, RFQ, websocket quotes, confirmation within seconds, the combo fee), same-game combinations, partial settlement of voided legs, an automatic "best ticket" suggestion (it can come later: the top flagged games into one ticket in one click).

## Decisions for you

1. Approve this design?
2. Defaults: at most 4 legs and at most one leg per game. The client decides; a question for him is drafted below.
3. The demo he asked for: see the notes in the reply.

**Draft question for the client:**
-> How many games do you usually put in one combo?
-> Do you ever put two bets on the same game in one combo, for example the winner and total goals?
