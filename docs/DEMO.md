# Demo script for the client (about 15 minutes, screen share)

The client asked for a demo before he gives feedback ("it will make more sense for me to either ask questions or modification"). The app runs only on the operator's computer (addresses `127.0.0.1`), so the demo is a **screen share on a call**; a recording of the same walk-through can be sent afterwards. Do not expose the app to the internet for this.

## Before the call (15 minutes)

- `docker compose up -d --build`, then check `docker compose ps` and `curl http://127.0.0.1:8000/health`.
- Kalshi must be reachable (it needed a VPN during development) and the OpenAI account must have credit (a run costs about 0.35 to 0.65 USD).
- Research 3 or 4 games that start in the next few hours (the forecast must be less than 12 hours old, or a ticket cannot be prepared from it) (press Research on the Games page, about 90 seconds each, two at a time), so the Opportunities page and the Approval screen have live content. Prefer games with a lot of volume: tour-level tennis, a Premier League or Champions League game, an MLB game.
- Run `docker compose exec backend uv run --no-sync python -m app.cli resolve-records` and `score-records` and note the numbers; if fewer than 30 games are finished, say so before he asks. Status on 2026-10-14: 30 games researched, 15 scored (first scores: ours 0.19, plain AI 0.22, Kalshi 0.15 on the Brier score, lower is better; flagged bets lost money so far); the rest finish by the morning of 2026-10-15.
- Sign in with the demo account and you land on the Dashboard; open the Games page and leave the browser there. Hide other tabs and any window showing `.env` or keys.

## The walk (what to show, what to say)

1. **Games** (2 min). One row per game with start time in his time zone, buy and sell prices, our estimate where researched. "This is where you pick a game. Pressing Research costs about 40 cents of OpenAI credit and takes about a minute and a half."
2. **A result page** (4 min). Open a researched game. Top to bottom: the forecast table (our probability against the market, the range of the three forecasts, the gap after fees, the flag); the forecasts, including the plain AI call with no research; the evidence, each claim with its check result; the pages we could not read. Say plainly: "Worth a look is not a recommendation. In our first tests the forecasts were close to a plain AI answer and often further from the truth than the market price; the scores will tell us whether it is any better."
3. **More markets** (1 min). Total goals or runs, both teams to score, margin of victory, shown as separate tables; tie and no tie are the two sides of the Tie market.
4. **Opportunities** (2 min). Researched games ranked by the gap at today's prices, one row per game, the risks in words; the recent alerts section; "alerts will go to Telegram".
5. **Approval** (3 min). Prepare an order from a flagged row; show the exact order in words, the checks, Approve, then Place in the simulation; show that pressing Place again is refused. "Nothing is ever sent to Kalshi. A real order is a later milestone and needs your decisions on limits."
6. **Tickets (combos)** (4 min). He builds combos of up to 17 bets, so show his way of working. On Opportunities press "Add" on a few games; the ticket panel at the bottom shows the combined chance and price, and keeps the legs while you move to a run page. On a run page add "yes" or "no" on any market (winner, total goals, both teams to score), including two markets of one game: the panel then says the combined numbers are rough because bets on the same game move together. Press Prepare ticket and go to Approval: each leg is listed with its own checks. Say plainly: "The ticket price here is the legs multiplied. A real Kalshi combo is quoted when you ask for it, and it is usually worse." Up to 20 legs; from 15 legs it says "wins about 1 time in N".
7. **Results and scores** (1 min). The Results page, and the numbers from `score-records` if there are enough games.

## Questions to ask him during the demo

- Which leagues and tours, and which US state (still open).
- The most he wants to risk on one bet and in one day (the screen uses placeholders: 10 contracts, 5 dollars, 20 dollars).
- Which basketball leagues he means (he said combos can include basketball; not built, we first need to know whether our forecasts beat the market on the three sports we have).
- Whether he adds only flagged games to a ticket or any game from the ranking (his example slip had mostly favourites at 78% to 96%, which we do not flag).
- What he wants on the Opportunities page that is not there.
- Whether he wants alerts for every kind of event or only when something is worth a look.

## Already answered by him (2026-10-13)

- A combo has up to 17 markets, may hold several bets on one game (winner, total goals, both teams to score) and may mix sports.

## Things not to say or show

- Do not promise profit. The honest position: the system may be a good research assistant and not a way to beat the market; the scores decide.
- Do not show `.env`, the Kalshi key file, the Telegram token or the database.
- Do not call a gap an opportunity unless the page flags it, and even then it is only "worth a look".
