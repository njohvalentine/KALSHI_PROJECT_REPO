# Spec: bigger tickets, as the client builds them (FEAT-20261014-0910 and FEAT-20261014-0911)

Branch `feature/sports-games-list` (base `master`). For approval; nothing here is built yet. Follows `FEAT-20261013-1838-bet-tickets.md`, which limited a ticket to at most 4 legs and one leg per game.

## What the client said (2026-10-13, 18:55 to 18:56) and showed

"17 markets on one tickets"; "yes some games has more than one bet, who will win, total goals and even both sides to score for example"; "a combo can also include soccer, base ball, basket ball tenis games". His example slip has legs of 78% to 96% (mostly favourites and "over 0.5 goals"), several from the same league and some from the same game, and most of them are not ones we would flag.

## Verified against the code (not assumed)

- `prepare_ticket` refuses two legs of one game (it compares `game["event_ticker"]`), `checks_for` has the same rule (`legs_ok`), and `TICKET_MAX_LEGS` is validated at most 10 in `config.py`, `PrepareBody.legs` is limited to 10.
- The side of a leg is never chosen by the person: `prepare_ticket` uses `market["side"]`, the side with the larger gap. His slip needs the "yes" on "over 0.5 goals" even when "no" has the larger gap.
- The Opportunities page lists one row per game with only its best market (`build_row`), so most markets of a game cannot be put on a ticket. The run page has no ticket button, only `PrepareOrder` on flagged markets. The ticket panel lives only on the Opportunities page.
- A leg's `event_ticker` is stored as the game's event (`p["game"]["event_ticker"]`) even for a total or both-teams-to-score market, which belongs to a companion Kalshi event (`_event_of(market_ticker)`).

## What Kalshi says (read 2026-10-14; docs.kalshi.com and third-party descriptions, to be read again at Milestone 7)

No official limit on legs was found; a third party saw 2 to 35 legs in traffic. Same-game legs are allowed, and the market makers who answer a request for a quote price the link between the legs privately. So a real quote for a ticket with same-game legs differs from our multiplied price in a way we cannot know.

## Design

1. **Legs.** `TICKET_MAX_LEGS` default 20, accepted up to 30; the API accepts up to 30 legs. Still a placeholder.
2. **Rule for legs.** A ticket may have at most **one leg per Kalshi event** (`_event_of(market_ticker)`): the winner event, the total event and the both-teams-to-score event of a game are different events and may all be on one ticket. Two legs of one event (for example "Home wins" and "Away wins", or "over 1.5" and "over 2.5") are either impossible together or repeat each other, so they are refused with a plain message. The same market twice stays refused. `order_legs.event_ticker` now stores the market's own event.
3. **Side.** A leg may carry `side` ("yes" or "no"); without it the best side is used as today. A side without a price is refused. `still_worth_a_look` is true only if the market is flagged **and** the chosen side is the flagged side.
4. **Rough numbers.** The combined probability stays the product of the legs. When two or more legs belong to one game the ticket is marked `rough` (API field `same_game_legs`: the number of games with more than one leg). The pages say: "Some games have several bets on this ticket. Those bets move together, so the combined chance and price here are rough, and a real Kalshi quote will differ in a way we cannot predict." I do **not** build a correlation model: we have no data for one. (Option not taken: show the possible range of the joint chance of linked legs; it adds a lot of text and the client has not asked for it. It can be added later.)
5. **Warnings.** Three or more legs: errors multiply. Fifteen or more: the combined chance is shown as "about 1 in N" so it is read for what it is. At 17 legs of 80% the ticket wins about 2% of the time.
6. **Building the ticket.** The ticket holder moves from the Opportunities page into the app layout and keeps its legs in the browser's session storage (wrapped in try/catch; the page works without it). "Add to ticket" appears on every priced market of the run page (buttons "yes at 42¢" and "no at 59¢"), and stays on the Opportunities rows (best market, best side). One ticket panel shows everywhere. The panel no longer needs the leg limit from the server; the server refuses too many legs with a clear message.
7. **Checks, approval, settlement:** unchanged in shape. The per-leg checks apply to every leg; settlement works for any number of legs.

## Not changed or not done

- Basketball (WISH-20261014-0912): not started; question to the client. `SPORTS_SERIES` already takes any Kalshi series for the Games list, but the research and the market kinds were written for soccer, baseball and tennis, so I will read them before promising anything.
- The real combo order and price (Milestone 7).
- Betting limits for a 17-leg ticket (max cost per order) are still the placeholders.

## Tests

Backend: legs of one game in different events allowed; two legs of one event refused; a chosen side used and a side without a price refused; `same_game_legs` counted; 20 legs accepted, 21 refused; the old "same game" test changed to "same event". Web app: lint and build and a manual check with screenshots.

## Checks to state at close

Lateral spread: every place that assumes one leg per game (prepare, `checks_for`, settle, the Results and Approval pages, the monitor). Causal depth: the client's need is "build the slip I build on Kalshi", which needs more than the limit (sides, any market, several pages), so the three items are one spec.

## Result (2026-10-14)

Built as specified. Backend: `TICKET_MAX_LEGS` 20 (up to 30), one leg per Kalshi market group (`_event_of`), a chosen side per leg, `same_game_legs` on every ticket, one read of Kalshi per game however many legs it has, `still_worth_a_look` true only for the flagged side. Web app: the ticket lives in the app layout and keeps its legs in session storage; every priced market on the run page has "Add yes" and "Add no" buttons; the panel shows the rough-number note and, from 15 legs, "about 1 time in N". 489 backend tests pass (6 new or changed); the web app is checked by lint and build only, **not yet looked at in a browser**.

Checks done: lateral spread (every place that assumed one leg per game: prepare, `checks_for`, the title of a ticket, the pages; settlement and the monitor never did); causal depth (the limit alone would not have been enough: sides and any-market choice were also missing). Not done: legs already migrated from the first tickets keep the game's group in `order_legs.event_ticker` (only one old order exists and it is closed, so it cannot clash). Basketball is not started.
