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

Limits that protect you: at most 2 runs at the same time (`MAX_CONCURRENT_RUNS`), at most one active run per game, at most 4 researchers per run.

**Automatic research** (`AUTO_RESEARCH_MAX_PER_DAY`) is **off** (0). If you set it above 0 with the watcher on, the system starts that many runs per day by itself, soonest games first. It spends money without anyone pressing a button, so set it deliberately.

## 6. The watcher and alerts

The watcher is off unless `MONITOR_ENABLED=true`. When on, it looks every `MONITOR_INTERVAL_MINUTES` (10) at the games that were researched and have not started, with today's prices, and records alerts in the app (the Opportunities page, "Recent alerts"). Alerts are also sent to Telegram when `ALERTS_ENABLED=true` (see below); otherwise an alert only appears there. The Opportunities page shows whether the watcher is on, when it last looked and the kind of error if its last look failed (the full text is in the backend log).

### Telegram alerts (set up once)

1. In Telegram, open **@BotFather**, send `/newbot`, pick a name; it gives you a **token**. The token is a secret: it goes only into `.env`, never into chat, e-mail or the code.
2. Open your new bot in Telegram and press **Start** (a bot cannot message a person who has not).
3. Put `TELEGRAM_BOT_TOKEN=<the token>` in `.env`, then run `docker compose up -d` and `docker compose exec backend uv run --no-sync python -m app.cli telegram-chat-id`. It prints `TELEGRAM_CHAT_ID=<number>`.
4. Put that line in `.env` too, add `ALERTS_ENABLED=true` and `MONITOR_ENABLED=true`, and run `docker compose up -d` again. If a value is missing or wrong the backend refuses to start and says which.

The Opportunities page then shows "Alerts are also sent to Telegram" and each alert in the history is marked Sent, or "Could not be sent" with the kind of error (`TelegramUnauthorized`: wrong token; `TelegramChatNotFound`: wrong chat id or Start not pressed; `TelegramBotBlocked`; `TelegramRateLimited`; `TelegramNetworkError`). The token is hidden from the logs and never shown on a page.

## 7. Looking at results

- **Games**: upcoming games with prices and, where researched, our estimate.
- **Opportunities**: researched games ranked by the gap after fees at today's prices. "Worth a look" is not a recommendation.
- **Prediction**: every run; open one for the forecast, the comparison with the market, the forecasts, the evidence with each claim's check result, and the pages that could not be read.

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

Off by default. To switch on, put `ODDS_ENABLED=true` and `ODDS_API_KEY=<your key>` in `.env` (the key is a secret) and run `docker compose up -d`; the app refuses to start if the key is missing or odd. Each researched game then saves, with its forecast, the consensus of the bookmakers (margin removed, exchanges left out) and Pinnacle's price, for winner markets in the leagues the feed lists (Premier League, Champions League, Europa League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, MLB, NPB, KBO and the ATP and WTA tournaments that are running; **not Challengers**). A game that does not match, or a feed error, saves the reason and never fails the run. One read of a league costs one credit per region and is shared by the games researched within `ODDS_CACHE_MINUTES`; the free plan has 500 credits a month and the log warns below 50. `score-records` prints how many outcomes have a bookmaker price and the scores of ours, the plain AI, Kalshi and the bookmakers on the same outcomes.

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

Use the values from your `.env` for USER, PASSWORD and the host port (`DB_HOST_PORT`). Each test makes and drops its own throwaway database. The web app has no automated tests yet, only lint, build and manual checks.

## 12. Before this is used for anything real

Not done yet, in this order of importance:
1. Kalshi's Developer Agreement has not been read, and it must be before any real order.
2. The Kalshi key that was shared in a chat must be replaced by a new one, and the old one revoked. Real keys are never kept in the code or in chat.
3. Betting limits and the rule for going live are not agreed (the approval screen exists, with placeholder limits, but only simulates orders; the real order step does not exist and is Milestone 7).
4. Handover: remove the development key file and the key lines from the development `.env`; do not hand over `.env`; the client creates their own keys, a new `SESSION_SECRET` and a new database password; set `SESSION_COOKIE_SECURE=true` and serve over HTTPS; replace the demo account.
