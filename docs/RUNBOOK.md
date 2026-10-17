# Operator run guide

How to run, check and look after the system. Written for the person who runs it day to day. For what the system does and why, read `docs/ARCHITECTURE.md`; for the decisions behind it, `docs/discussion/NOTEPAD.md`.

Nothing in this system places an order on Kalshi. Kalshi is only read. The approval screen exists, but its orders are **simulated**: there is no trading code at all.

---

## 1. What runs where

| Part | What it is | Where |
|---|---|---|
| `db` | PostgreSQL 17, the only place data lives (volume `db_data`) | host port `127.0.0.1:${DB_HOST_PORT}` (for tests only) |
| `backend` | the API, the research runs, the watcher | `http://127.0.0.1:8000` |
| `frontend` | the web app | `http://127.0.0.1:3000` |

All three start together with Docker Compose. Nothing is reachable from the network: every port is bound to `127.0.0.1`.

## 2. Start, stop, check

```
docker compose up -d --build      # start everything (rebuilds what changed; database migrations run when the backend starts)
docker compose ps                 # all three should be "Up", db "healthy"
curl http://127.0.0.1:8000/health # {"status":"ok","db":true}
docker compose logs -f backend    # follow the backend log (Ctrl+C to leave it)
docker compose down               # stop (the data stays in the volume)
```

`docker compose down -v` also deletes the database. Do not use `-v` unless you mean it.

The first lines of the backend log say what is on and off: whether research is on (needs `OPENAI_API_KEY`), whether LangSmith tracing is on, how many leagues are configured, and whether the watcher and automatic research are on.

## 3. Settings

Everything is set in the file `.env` next to `docker-compose.yml` (git-ignored; never commit it, never paste its contents anywhere). `.env.example` lists every setting with a comment and its default. After changing `.env`, run `docker compose up -d` again.

Settings the app **requires** (it refuses to start without them, and says which is wrong): `DATABASE_URL` (built by Compose from the `POSTGRES_*` values), `KALSHI_API_BASE`, `SESSION_SECRET` (at least 32 random characters), and `LANGSMITH_API_KEY` when `LANGSMITH_TRACING=true`.

Without `OPENAI_API_KEY` the app starts, the Games page works, and pressing Research is refused with a clear message.

Groups of tuning settings (all have safe defaults): models and limits for research, page reading (`FETCH_*`), claim checking (`CHECK*`), forecasters (`FORECASTER_*`), when a gap is called "worth a look" (`EDGE_MIN`, `MIN_SUPPORTED_CLAIMS`, `MIN_ASK_SIZE`, `MIN_RESEARCH_SHIFT`, `EDGE_PLAUSIBLE_MAX`; **placeholders until the accuracy test has scored real forecasts**), the Opportunities page (`OPPORTUNITY_MAX_AGE_HOURS`), the watcher and alerts (`MONITOR_*`, `ALERT_*`), automatic research (`AUTO_RESEARCH_*`), and the list of leagues (`SPORTS_SERIES`).

## 4. Accounts

There is no registration page. Accounts are made with a command, run inside the backend container:

```
docker compose exec backend uv run --no-sync python -m app.cli create-user someone@example.com
docker compose exec backend uv run --no-sync python -m app.cli set-password someone@example.com
```

Both ask for the password twice. Passwords are stored hashed (Argon2). Five wrong passwords lock the account for 15 minutes; `set-password` unlocks it. Changing a password signs out every session of that account.

## 5. Costs

Every run spends OpenAI credit. Measured on real games (2026-10-13): about **0.35 to 0.65 USD per game** (research about 0.3 to 0.4, claim checking 0.01 to 0.12, forecasters about 0.1, the plain-AI comparison about 0.01). The run page shows the cost per stage. A run above `RUN_COST_WARN_USD` (3.00) is flagged.

Limits that protect you: at most 5 games researched in any 24 hours, by a person or the watcher (`RESEARCH_MAX_PER_DAY`, 0 = no limit; a run that failed still counts, because it may have spent credit, and the message says when the next slot opens), at most 2 runs at the same time (`MAX_CONCURRENT_RUNS`), at most one active run per game, at most 4 researchers per run. The Dashboard shows how many of the limit are used. A game whose forecast is still fresh (less than `OPPORTUNITY_MAX_AGE_HOURS`, 12) is not researched again unless a person confirms: the server answers with the age and the cost of the last run, the button asks "Research again anyway?", and the watcher is always refused.

**Automatic research** (`AUTO_RESEARCH_MAX_PER_DAY`) is **off** (0). If you set it above 0 with the watcher on, the system starts that many runs per day by itself, soonest games first. It spends money without anyone pressing a button, so set it deliberately.

## 6. The watcher and alerts

The watcher is off unless `MONITOR_ENABLED=true`. When on, it looks every `MONITOR_INTERVAL_MINUTES` (10) at the games that were researched and have not started, with today's prices, and records alerts in the app (the Opportunities page, "Recent alerts"). Alerts are also sent to Telegram when `ALERTS_ENABLED=true` (see below); otherwise an alert only appears there. The Opportunities page shows whether the watcher is on, when it last looked and the kind of error if its last look failed (the full text is in the backend log).

### Telegram alerts (set up once)

1. In Telegram, open **@BotFather**, send `/newbot`, pick a name; it gives you a **token**. The token is a secret: it goes only into `.env`, never into chat, e-mail or the code.
2. Open your new bot in Telegram and press **Start** (a bot cannot message a person who has not).
3. Put `TELEGRAM_BOT_TOKEN=<the token>` in `.env`, then run `docker compose up -d` and `docker compose exec backend uv run --no-sync python -m app.cli telegram-chat-id`. It prints `TELEGRAM_CHAT_ID=<number>`.
4. Put that line in `.env` too, add `ALERTS_ENABLED=true` and `MONITOR_ENABLED=true`, and run `docker compose up -d` again. If a value is missing or wrong the backend refuses to start and says which.

5. To check that delivery works without waiting for a real alert, send one hello message: `cd backend && set -a; source ../.env; set +a; uv run python ../scripts/telegram_hello.py`. It prints whether each value is set (never the values), says "Sent: check Telegram." or names what is wrong (wrong token, wrong chat id or Start not pressed, bot blocked, Telegram not reachable). It uses the same sender as the alerts.

The Opportunities page then shows "Alerts are also sent to Telegram" and each alert in the history is marked Sent, or "Could not be sent" with the kind of error (`TelegramUnauthorized`: wrong token; `TelegramChatNotFound`: wrong chat id or Start not pressed; `TelegramBotBlocked`; `TelegramRateLimited`; `TelegramNetworkError`). The token is hidden from the logs and never shown on a page.

## 7. Looking at results

- **Dashboard** (the page after sign-in): how the forecasts compare with the Kalshi price. Four cards (finished games scored, researched games worth a look today, flagged bets, research spend) and two bar charts (all games, and by sport; Brier score, lower is better). The line at the top is written by the app from the scores: "too few to say anything yet" below 30 finished games; "ahead of the Kalshi price" only when our score is at least 0.005 better than Kalshi's (a smaller gap counts as noise, and the line still says it is not proof); otherwise "No sign of an edge yet". The numbers come from the same code as `score-records`. The research spend is the app's own calculation from the tokens used, not the OpenAI bill; compare it with the OpenAI usage page now and then.
- **Games**: upcoming games with prices and, where researched, our estimate.
- **Opportunities**: researched games ranked by the gap after fees at today's prices. Every game has one answer, the same on the run page and in the alerts: **NO BET** (no market passed the tests, the forecast is more than 12 hours old, or there is no forecast or price), or **Worth a look**. A game that is worth a look carries the caution "NO BET is the default: ..." until the finished games show that our forecasts beat the Kalshi price (the Dashboard's message says "ahead") and while its sport has no scored results. "Worth a look" is never a recommendation to bet.
- **Prediction**: every run; open one. A finished run opens with an "At a glance" box (how many markets are worth a look and the best ones, how many facts their pages supported, time and cost), then the forecast and the market (the first kind of market open, the others folded with a count of the markets worth a look), and folded sections for how the flag is decided, the forecasts side by side, the evidence with each claim's check result, the pages we tried to read, and what was researched. Nothing is removed; open a section to read it.
- **Approval**: orders waiting for a person (with their checks, Approve and Reject) and a table of the recent orders.
- **Results**: simulated orders and what they would have paid, with cards for the settled orders, the chosen side at the ask over all scored outcomes, and the flagged bets.

## 8. Scoring the forecasts

Every run with a forecast saves a record (our probabilities, the market price at that moment, the plain-AI comparison). After the games finish:

```
docker compose exec backend uv run --no-sync python -m app.cli resolve-records   # fills in who won (read-only on Kalshi)
docker compose exec backend uv run --no-sync python -m app.cli score-records     # prints the scores
docker compose exec backend uv run --no-sync python -m app.cli score-records --since 2026-10-13
```

`resolve-records` looks at games that started more than `RESOLVE_AFTER_HOURS` (3) ago and can be run as often as you like. `score-records` prints Brier scores (lower is better) of our probability, the plain-AI call and Kalshi's price on the same outcomes, per kind of market, and what buying the chosen side at the ask would have paid. Below about 30 games it says there is too little to conclude anything; do not read more into it than that.

## 8b. Simulated orders and the approval screen

From an Opportunities row (or a flagged row of a run page) a person presses **Prepare order** with a number of contracts. The order waits on the **Approval** page with its checks (not expired, game not started, forecast recent, within the limits, price has not moved against us, enough contracts offered, still worth a look). A person presses Approve or Reject; an approved order is placed in the simulation by a separate press, which records a simulated fill at the price of that moment. An order not approved and placed within `ORDER_EXPIRY_MINUTES` (10) expires. The history of every change is kept (`order_events`). When the game has ended, `resolve-records` also settles the simulated orders, and the Results page shows what they would have paid.

The limits are settings in `.env.example` (`ORDER_MAX_CONTRACTS`, `ORDER_MAX_COST_USD`, `ORDER_MAX_DAY_COST_USD`, `ORDER_EXPIRY_MINUTES`, `ORDER_MAX_SLIPPAGE_CENTS`). **They are placeholders until the client has agreed his own.** Nothing here sends anything to Kalshi.

### Tickets of several games

On the Opportunities page or on a run page, **Add “yes” / Add “no”** on up to `TICKET_MAX_LEGS` (20) markets, then **Prepare ticket** in the panel at the bottom (it stays while you move between pages). A ticket pays only if every leg wins. It may hold several markets of one game (winner, total, both teams to score) but only one from each group of markets; when it does, its combined numbers are marked rough because those legs move together. Its price and chance are the legs multiplied, and the fee uses the dearest leg's fee type. This is the simulation's price; a real Kalshi combo is quoted on request and is usually worse. The Approval page shows each game with its own checks. A ticket is lost as soon as one game is lost; if a game is voided the stake is returned.

### Bookmaker benchmark (The Odds API)

Off by default. To switch on, put `ODDS_ENABLED=true` and `ODDS_API_KEY=<your key>` in `.env` (the key is a secret) and run `docker compose up -d`; the app refuses to start if the key is missing or odd. Each researched game then saves, with its forecast, the consensus of the bookmakers (margin removed, exchanges left out) and Pinnacle's price, for winner markets in the leagues the feed lists (Premier League, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, NPB, KBO and the ATP and WTA tournaments that are running; **not Challengers**). A game that does not match, or a feed error, saves the reason and never fails the run. One read of a league costs one credit per region and is shared by the games researched within `ODDS_CACHE_MINUTES`; the free plan has 500 credits a month and the log warns below 50. `score-records` prints how many outcomes have a bookmaker price and the scores of ours, the plain AI, Kalshi and the bookmakers on the same outcomes. Each run now also compares the bookmakers with the Kalshi price per winner market: the gap against them after fees (buying "yes" is worth the bookmakers' probability minus the ask minus the fee, and the same for "no"), whether enough contracts are offered, and whether they agree with our side. It is shown on the run page ("Bookmakers" section, or the reason there is none), on the Opportunities row when the best market is a winner market (with the age of the bookmaker read), and on the Dashboard ("Games with bookmaker prices", scored as games finish). It does not change the flag. The bookmaker price is read once per run, before the Kalshi comparison.

### Replaying the forecasts on saved evidence

To try an idea (more forecasters, another model or effort, other flag limits) without waiting for new games, re-run only the forecasting step and the flag rule on the evidence and prices saved before each finished game. A fresh run on a finished game would let the web search find the result; a replay cannot, because everything it reads was saved before the game. Nothing is written back.

```
docker compose exec backend uv run --no-sync python -m app.cli replay-forecasts --rules-only                       # free: only the flag rule, current or changed limits
docker compose exec backend uv run --no-sync python -m app.cli replay-forecasts --forecaster-count 5               # prints the model calls and an estimate, spends nothing
docker compose exec backend uv run --no-sync python -m app.cli replay-forecasts --forecaster-count 5 --yes         # spends it (about 0.01 to 0.03 USD per forecaster call)
docker compose exec backend uv run --no-sync python -m app.cli replay-forecasts --tune-until 2026-10-14T12:00 --yes # only the games made up to then
docker compose exec backend uv run --no-sync python -m app.cli replay-forecasts --tune-until 2026-10-14T12:00 --final --yes  # later games only: the test set, once the settings are fixed
```

Other options: `--forecaster-model`, `--forecaster-effort`, `--edge-min`, `--min-supported-claims`, `--min-research-shift`, `--edge-plausible-max`, `--min-ask-size`, `--created-after`, `--created-before`. It prints the Brier scores of the replay, the original forecast, the plain AI call and Kalshi on the same outcomes, and what the flagged markets would have paid. Models are not deterministic and a few games fit noise: choose the candidate settings on the early games, write them down, then look at the held-back games once.

### Other sports on Kalshi

The Games page shows the measured series (`SPORTS_SERIES`, the 15 we have scores for) as before, and a row "More on Kalshi" with every other sport or league Kalshi lists, with the number of games coming up. Picking one loads its games (the first load asks Kalshi about each series and takes up to about 20 seconds; at most 60 series at once, the busiest first). Those games can be researched like any other; they are marked **not yet measured** until the sport has `MEASURED_MIN_GAMES` (20) scored games, and the flag, the Opportunities row, the run page and the Telegram alert say so. The NBA has its total points and spread markets; other new sports get the winner market only. `SPORTS_DISCOVERY=false` gives the old list exactly; `SPORTS_EXCLUDE_TAGS` leaves out sport tags (default Esports, Video games, 4th of July, Other). Automatic research and the daily batch still use only the measured series.

## 9. Backups

The database holds everything (runs, sources, forecasts, records, alerts, accounts). A backup:

```
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

Run it from the folder with `.env` loaded (`set -a; source .env; set +a`). Keep the file somewhere safe: it contains account hashes and everything the system read. Restore into an empty database with `psql`. Nothing in the app depends on files outside the database.

## 10. When something goes wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| Games page says leagues could not be loaded, or loads slowly | Kalshi unreachable or slow from this machine (it needed a VPN during development) | Reload; check the machine can open `https://external-api.kalshi.com`; the page still shows the leagues that did load |
| Pressing Research says research is not configured | `OPENAI_API_KEY` missing | Add it to `.env`, `docker compose up -d` |
| A run is marked "failed" with a short kind of error | OpenAI or a network problem; the page shows only the error kind | `docker compose logs backend` has the full text |
| A run is marked failed "Interrupted by a restart" | the backend restarted while it ran | start it again; nothing was lost except that run |
| "No forecast for this game" with a reason | fewer than two valid forecasts, or checking is switched off | read the reason; the research below is still valid |
| Almost no claim is "supported" | the cited pages were menus only, blocked, or PDFs | see the pages list on the run page; bookmaker pages usually block automatic readers |
| Backend will not start | a required setting is missing or wrong | the log names every problem |
| Login says "Too many attempts" | five wrong passwords | wait 15 minutes or run `set-password` |

Never run `pkill -f pytest` on this machine: it kills the shell that runs it.

## 11. Tests

```
cd backend && TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:55432/valentine uv run pytest -q   # the database from Compose must be up
cd frontend && BACKEND_INTERNAL_URL=http://127.0.0.1:8000 npm run lint && BACKEND_INTERNAL_URL=http://127.0.0.1:8000 npm run build
```

Use the values from your `.env` for USER, PASSWORD and the host port (`DB_HOST_PORT`). Each test makes and drops its own throwaway database.

The web app has browser tests (Playwright) that drive the running stack: sign-in, the ticket builder, the Approval flow. Once: `cd frontend && npm ci && npx playwright install chromium`. Make a test account (`docker compose exec -T backend uv run --no-sync python -m app.cli create-user e2e@example.com --password-stdin`, then type the password into stdin), start the stack (`docker compose up -d`) and run `E2E_EMAIL=e2e@example.com E2E_PASSWORD=... npm run test:e2e` from `frontend/`. The tests prepare a real simulated ticket and reject it; nothing is placed and nothing reaches Kalshi. A test that needs a game open for a ticket skips itself with the reason when there is none.

## 12. Before this is used for anything real

Not done yet, in this order of importance:
1. Kalshi's Developer Agreement has not been read, and it must be before any real order.
2. The Kalshi key that was shared in a chat must be replaced by a new one, and the old one revoked. Real keys are never kept in the code or in chat.
3. Betting limits and the rule for going live are not agreed (the approval screen exists, with placeholder limits, but only simulates orders; the real order step does not exist and is Milestone 7).
4. Handover: remove the development key file and the key lines from the development `.env`; do not hand over `.env`; the client creates their own keys, a new `SESSION_SECRET` and a new database password; set `SESSION_COOKIE_SECURE=true` and serve over HTTPS; replace the demo account.
