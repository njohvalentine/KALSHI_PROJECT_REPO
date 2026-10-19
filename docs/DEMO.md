# Demo script for the client (about 20 minutes, screen share)

The client asked for a demo before he gives feedback. The app runs on the operator's computer (`127.0.0.1`), so the demo is a **screen share on a call**; a recording of the same walk-through can be sent afterwards. Do not expose the app to the internet for this. (The server at the deployed address still shows the old look until it is redeployed.)

The client's own question is whether the application can consistently find real opportunities. The demo shows the machinery and answers that question honestly; it does not sell.

## Before the call (the day before, and 15 minutes before)

- `docker compose up -d --build`, then `docker compose ps` and `curl http://127.0.0.1:8000/health`. Kalshi must be reachable (it needs a VPN here).
- The OpenAI account needs credit. A run costs about 0.26 to 0.63 USD.
- **The daily limit counts the last 24 hours (5 games by default).** Research the demo games **the day before**, so the limit is not used up during the call. Do not plan to research live; if you do, say that the limit exists on purpose. Pick games that start within about 12 hours of the call (older forecasts cannot be turned into a ticket), with plenty of volume: tour-level tennis, a Premier League or Champions League game, an MLB game.
- Run `docker compose exec backend uv run --no-sync python -m app.cli resolve-records` and `score-records` and write the numbers down. Status on 2026-10-19: 71 games scored; Brier score (lower is better) on the 553 outcomes with all three: ours 0.1942, plain AI 0.1953, Kalshi price 0.1757; the chosen side at the ask lost 6.4 cents per contract on average (557 bets); the 43 flagged bets lost 11.4 cents per contract. Use today's numbers, not these.
- Press "Check these games against the bookmakers" on the Games page once (it uses a few Odds API credits) so the check has saved results.
- Fallback if Kalshi or the VPN fails during the call: the screenshots in `docs/design/screenshots-2026-10-16/` (sign-in, dashboard, games, opportunities, prediction list, run page, approval, results; desktop and phone).
- Sign in with the demo account (you land on the Dashboard). Hide other tabs and any window showing `.env`, keys, or `docker compose logs backend` (the log can hold the Telegram token).

## The walk (what to show, what to say)

1. **Opening, honest (2 min).** Say the finding first. "So far our forecasts are not better than the Kalshi price: on 71 finished games the price scores 0.176, ours 0.194. I also tested 4,709 old Kalshi games for free, and found no pattern that pays after fees. The bookmakers match Kalshi. So the app is a research assistant that has not yet shown an edge, and the point of the next weeks is to find out, cheaply."
2. **Dashboard (3 min).** The scores against the Kalshi price, the paper result of the flagged bets, accuracy by sport and by kind of market, the bookmakers block, the spend of the last 24 hours against the daily limit, and what is worth a look today. "Too few games" is shown where a group is small: say it out loud.
3. **Games (3 min).** One row per game with the start time, prices and our estimate where researched. Show the free bookmaker check (the button above the table): a column says whether a game looks worth researching. "This costs no OpenAI credit. On 53 games it found none worth the cost of research." Show that Research on a game already researched in the last hours asks to confirm, and that the daily limit is visible.
4. **A result page (5 min).** Top to bottom: the **verdict** (NO BET, or Worth a look with its caution), the forecast table (our probability against the market, the range of the three forecasts, the gap after fees), the **Bookmakers** fold (the fair price from the bookmakers next to Kalshi), the forecasts including the plain AI call without research, the evidence with each claim's check, the pages we could not read. Say: "Worth a look is not a recommendation."
5. **More markets and Opportunities (2 min).** Total goals or runs, both teams to score, margin of victory as separate tables. Opportunities: researched games ranked by the gap at today's prices, the verdict on each row, the recent alerts ("alerts go to Telegram").
6. **Approval (3 min).** Prepare an order from a flagged row: the exact order in words and the checks, including the new ones (no stop rule has triggered, within the per-game limit, within the open limit). Approve, Place in the simulation, and show that pressing Place again is refused. "Nothing is ever sent to Kalshi. A real order is a later step and needs your decisions on limits; the proposed limits are in `docs/RISK-FRAMEWORK.md`."
7. **Tickets (combos) (2 min).** Add a few legs from Opportunities, then a market on a run page; the panel shows the combined chance and price, and says the numbers are rough when two bets are on the same game. Prepare ticket: each leg has its own checks. Say: "The ticket price is the legs multiplied; a real Kalshi combo is quoted when asked and is usually worse." Up to 20 legs.
8. **Results (1 min).** The simulated result by sport and by kind of market; the same numbers as the Dashboard, in more detail.

## Questions to ask him during the demo

- The values he wants for the limits in `docs/RISK-FRAMEWORK.md` (per order, per game, per day, open, stop for the day, stop completely), and for the evidence thresholds.
- Which leagues and tours, and which US state (still open).
- A new Kalshi key: ours is the production key and must be replaced before any real trading.
- Whether he adds only flagged games to a ticket or any game from the ranking.
- What he wants on the Opportunities page that is not there.
- The $20 OpenAI credit and the GitHub repository (his open requests).

## Already answered by him

- A combo has up to 17 markets, may hold several bets on one game and may mix sports (2026-10-13).
- His priority: whether the application can consistently identify genuine opportunities, not only provide research (2026-10-16). He set 5 researched games a day, one charge per game, a NO BET verdict, a bookmaker comparison, free screening, accuracy by sport and kind, and a risk framework for $100 in paper mode; all are built.

## Things not to say or show

- Do not promise profit. The honest position: a research assistant that has not shown an edge; the scores decide, and the 5-a-day plan grows the sample.
- Do not call a gap an opportunity unless the page flags it, and even then it is only "worth a look".
- Do not mention an in-game opportunity: the one test we ran had too few bets and its good numbers come from knowing when the game ended.
- Do not show `.env`, the Kalshi key file, the Telegram token, the backend log or the database.
