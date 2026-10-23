# Spec: updates when a game's forecast or price changes (FEAT-20261022-0958)

Working branch: the one checked out, `feature/security-hardening` (base `master`); the user decides on branches. From the client's message of 2026-10-22: "updates when important information changes" and, in his answer 4, **"change in forecast and price"**. Depends on the lineup update (FEAT-20261022-0956, built) and on the watcher (`app/monitor.py`, built).

## What is there now (read in `monitor.py`, `alerts.py`, the Opportunities page)

- The watcher (off unless `MONITOR_ENABLED`) reads today's prices of every researched game that has not started, every `MONITOR_INTERVAL_MINUTES` (10), and records four alerts, once per run and kind, with a cooldown and an hourly cap: `run_flagged`, **`market_moved`** (a market moved `ALERT_MOVE_CENTS` or more since our forecast), `no_longer_flagged`, `start_soon`. They go to the app and, when `ALERTS_ENABLED`, to Telegram. The Opportunities page lists the last ten.
- So **a price change is already covered.** What is missing: (1) nothing says when a **forecast** changed (a new run or an update gave different probabilities); (2) nothing says when a game is **due for a lineup update**, which is the one moment (about an hour before the start) when an update can find confirmed lineups; (3) nothing does the update by itself, so the measurement of whether lineup updates help depends on someone pressing a button at the right minute; (4) the Dashboard, which the client asked to show updates, shows no changes at all (only the Opportunities page does).
- What the watcher **cannot** do: detect news. It does not read news pages or injury reports between runs (that would be research on a timer, with a cost). "Important information" is therefore three things it can see: a **price move**, a **new forecast** that differs, and **the clock** (lineups are out).

## Design

1. **New alert `forecast_changed`.** When the newest run of a game (an update, or a repeat run) has a forecast and the game has not started, the watcher compares it with the run before (the one it updates, else the previous finished run of the same game). If any **match-result** probability (winner market; if none, any market) moved `ALERT_FORECAST_CHANGE_POINTS` or more (default 5 points), it raises one alert per run: *"Forecast changed: Torino vs Monza. After the lineup update Torino wins went from 49% to 41%, Monza wins from 22% to 28%. Verdict: NO BET. This is not a recommendation; nothing is ordered."* It carries the verdict of the new run, so a change that makes something worth a look is said plainly. The same cooldown, hourly cap and once-per-run rule as the other alerts apply. A smaller change raises nothing.
2. **New alert `update_due`.** For a game whose newest run has a forecast, with no update after it, that starts within `ALERT_UPDATE_DUE_MINUTES` (default 90) and whose forecast is older than 3 hours: *"Lineups are probably out for Torino vs Monza (starts in 80 minutes; forecast made 9 hours ago). Open the result page and press Update with lineups (about $0.20)."* Once per run.
3. **Optional automatic update, off by default.** `AUTO_UPDATE_MAX_PER_DAY` (default 0 = off): the watcher starts a lineup update for the same games as `update_due` (one per cycle at most, soonest start first), through the same `start_update` (so every refusal and the daily update limit `RESEARCH_UPDATES_MAX_PER_DAY` apply; the run is marked `auto`). Cap per UTC day like automatic research. At the measured cost (0.21 USD) a cap of 3 is about 0.63 USD a day. Reason for building it: the open question (do updates 45 to 90 minutes before the start find a confirmed lineup that passes the check, and do they improve the forecast) needs updates made at that minute, and nobody should have to be awake for that. It never starts a game that already has an update, a run in progress, or a forecast younger than 3 hours.
4. **The Dashboard shows what changed.** A card "What changed" with the last six alerts (price moves, forecast changes, updates due, flagged and no-longer-flagged), each with its age, the game (a link to its result page) and the first sentence; a link to the Opportunities page for all. The same alert rows, no new table.
5. **Settings** (all pass-through in `docker-compose.yml` without defaults there, listed in `.env.example`, tested): `ALERT_FORECAST_CHANGE_POINTS` (5), `ALERT_UPDATE_DUE_MINUTES` (90), `AUTO_UPDATE_MAX_PER_DAY` (0). `start_update` gets a `trigger` argument (manual or auto), the run record keeps it; no migration (the column exists).

## Not done

No news or injury-report watcher; no change to the price-move alert; no alert about the bookmakers' prices; no push other than Telegram; no change to the flag rule.

## Risks, stated now

Alerts can multiply: the cooldown and the hourly cap hold the extra ones back (recorded as held back, as today); an automatic update is real money, hence the default of off and the cap; a forecast change is not a signal that the new forecast is right (our record so far shows no edge), and the alert text says so.

## Checks to state at close

Lateral: every alert kind goes through `_raise` (once per run, cooldown, cap, Telegram or app only); every place that counts automatic runs (`Run.trigger == "auto"` in the research rule) must not count automatic updates as researched games (an update has `refresh_of` set; the research rule counts only runs without it). Causal depth: "important information changes" has three causes the system can see (price, forecast, the clock); the news itself it cannot see, and the item says so.

## Tests

`forecast_changed`: raised for a change at or above the threshold, not below it, only once per run, with the verdict, picks the match results first, ignores a game that has started and a first run with no earlier one; `update_due`: raised in the window with an old forecast, not outside it, not when an update exists, once per run; the automatic update: off by default, respects its cap and the update limit, starts the soonest game first, is marked `auto`, never counts as a researched game, skips a game with a run in progress or a young forecast; the three settings parse and are in the compose file; the Dashboard card reads the alert rows; the alert texts. Full suite, frontend lint and build, a screenshot of the card.
