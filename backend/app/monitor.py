"""The watcher: alerts and the optional automatic research. Off unless MONITOR_ENABLED is true.

Every cycle it reads fresh prices for the researched games that have not started (the Opportunities
code, no model call) and records an alert when something is worth saying:
- run_flagged: a game has markets worth a look at today's prices (a finished run, or a price that came to us),
- market_moved: a market moved ALERT_MOVE_CENTS or more since the forecast (the market may know
  something we do not, so the alert says to research again, not to bet),
- no_longer_flagged: the markets that were worth a look no longer are,
- start_soon: a game worth a look starts within ALERT_START_SOON_MINUTES (the forecast may be out of date).
Alerts are recorded in the app and, when ALERTS_ENABLED is true, also sent to Telegram through `deliver`.

Automatic research (AUTO_RESEARCH_MAX_PER_DAY, 0 = off) starts ordinary runs for the next games on a
plain rule. Each run costs real money, hence the explicit cap."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import Alert, Run
from app.opportunities import collect
from app.runs import RunStartError, start_game_run

log = logging.getLogger("app.monitor")

NOT_ADVICE = "This is not a recommendation; nothing is ordered."


def _cents(dollars: float | None) -> str:
    return "–" if dollars is None else f"{round(dollars * 100)}¢"


def _age(finished_at: datetime | None, now: datetime) -> str:
    if finished_at is None:
        return "at an unknown time"
    hours = (now - finished_at).total_seconds() / 3600
    return "less than an hour ago" if hours < 1 else f"{round(hours)} h ago"


def alert_text(kind: str, game: dict, row: dict, now: datetime, detail: dict) -> str:
    title, claims, age = game["title"], row["supported_claims"], _age(game["finished_at"], now)
    caution = f" {row['verdict']['caution']}" if row["verdict"]["caution"] else ""  # NO BET is the default while the flag has no track record
    if kind == "run_flagged":
        b = detail["best"]
        more = f" {b['count'] - 1} more market(s) of this game are also worth a look." if b["count"] > 1 else ""
        return (f"Worth a look: {title}. Buy “{b['side']}” on {b['market']} at {_cents(b['price'])}, gap {round(b['gap'] * 100):+d}¢ after fees."
                f"{more} {claims} supported claims. Forecast made {age}.{caution} {NOT_ADVICE}")
    if kind == "market_moved":
        return (f"The market moved {detail['cents']}¢ on {detail['market']} since our forecast of {title} ({age}). The forecast may be out of date: "
                f"the market may know something we do not. Consider researching again. {NOT_ADVICE}")
    if kind == "no_longer_flagged":
        return f"No longer worth a look: {title}. The markets we flagged no longer show a gap at today's prices (forecast made {age}). NO BET. {NOT_ADVICE}"
    return (f"Starting soon: {title}, worth a look at today's prices, but the forecast was made {age} and lineups may have changed. "
            f"Consider researching again.{caution} {NOT_ADVICE}")


class Monitor:
    def __init__(self, app):
        self.app = app
        self.status = {"last_cycle_at": None, "last_error": None, "auto_research_started_today": 0}

    # ---- alerts -------------------------------------------------------------------------------------------

    def _alerts_since(self, minutes: float, now: datetime) -> list[Alert]:
        with DbSession(self.app.state.engine) as db:
            return list(db.scalars(select(Alert).where(Alert.created_at >= now - timedelta(minutes=minutes))))

    def _seen(self, kind: str, run_id: str, told_only: bool = False) -> bool:
        """An alert of this kind for this run exists (held-back ones too, unless `told_only`)."""
        with DbSession(self.app.state.engine) as db:
            query = select(func.count()).select_from(Alert).where(Alert.kind == kind, Alert.run_id == run_id)
            if told_only:
                query = query.where(Alert.status != "held_back")
            return db.scalar(query) > 0

    async def deliver(self, text: str) -> tuple[str, str | None]:
        """Sends the text to Telegram when a notifier exists (ALERTS_ENABLED=true): (status, error kind). Without one
        the alert is only recorded in the app."""
        notifier = getattr(self.app.state, "notifier", None)
        if notifier is None:
            return "recorded", None
        try:
            await notifier(text)
            return "sent", None
        except Exception as exc:  # the kind only: the message may hold a token or a chat id
            log.warning("Sending an alert failed: %s", type(exc).__name__)
            return "failed", type(exc).__name__

    async def _raise(self, kind: str, game: dict, row: dict, now: datetime, detail: dict) -> None:
        s = self.app.state.settings
        if await asyncio.to_thread(self._seen, kind, game["run_id"]):
            return  # once per run and kind, also across restarts
        recent = await asyncio.to_thread(self._alerts_since, 60, now)
        counted = [a for a in recent if a.status != "held_back"]
        held = None
        if any(a.kind == kind and a.event_ticker == game["event_ticker"] and a.created_at >= now - timedelta(minutes=s.alert_cooldown_minutes) for a in counted):
            held = f"cooldown: an alert of this kind for this game was made in the last {s.alert_cooldown_minutes:g} minutes"
        elif len(counted) >= s.alert_max_per_hour:
            held = f"hourly limit of {s.alert_max_per_hour} alerts reached"
        text = alert_text(kind, game, row, now, detail)
        status, error = ("held_back", held) if held else await self.deliver(text)
        with DbSession(self.app.state.engine) as db:
            db.add(Alert(kind=kind, event_ticker=game["event_ticker"], run_id=game["run_id"], title=game["title"], text=text, status=status, detail=error))
            db.commit()
        log.info("Alert %s for %s: %s", kind, game["event_ticker"], status)

    async def alert_cycle(self, now: datetime) -> None:
        s, state = self.app.state.settings, self.app.state
        for game, comparison, row in await collect(state.engine, state.kalshi, s, state.fee_cache, now):
            if row["stale"] or "unavailable" in comparison:
                continue
            best = row["best"]
            if row["flagged"]:  # worth a look at today's prices under today's rules, like the Opportunities page
                await self._raise("run_flagged", game, row, now, {"best": {
                    "market": best["market"], "side": best["side"], "price": best["price"], "gap": best["gap"], "count": row["flagged_markets"]}})
            moves = []
            for c in comparison["outcomes"]:
                before = game["forecast_mids"].get(c["market_ticker"])
                if before is not None and c.get("yes_bid") is not None and c.get("yes_ask") is not None and 0 < c["yes_bid"] <= c["yes_ask"] < 1:
                    moves.append((abs((c["yes_bid"] + c["yes_ask"]) / 2 - before), c["market_ticker"]))
            if moves and max(moves)[0] * 100 >= s.alert_move_cents:
                ticker = max(moves)[1]
                label = next((o["outcome"] for o in game["prediction"]["outcomes"] if o["market_ticker"] == ticker), ticker)
                await self._raise("market_moved", game, row, now, {"cents": round(max(moves)[0] * 100), "market": label})
            if not row["flagged"] and await asyncio.to_thread(self._seen, "run_flagged", game["run_id"], True):
                await self._raise("no_longer_flagged", game, row, now, {})  # we told the user it was worth a look; now it is not
            start = game["start"]
            if row["flagged"] and start and now < start <= now + timedelta(minutes=s.alert_start_soon_minutes):
                await self._raise("start_soon", game, row, now, {})

    # ---- automatic research -------------------------------------------------------------------------------

    def _auto_started_today(self, now: datetime) -> int:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        with DbSession(self.app.state.engine) as db:
            return db.scalar(select(func.count()).select_from(Run).where(Run.trigger == "auto", Run.created_at >= midnight)) or 0

    def _recently_researched(self, tickers: list[str], now: datetime, hours: float) -> set[str]:
        with DbSession(self.app.state.engine) as db:
            return set(db.scalars(select(Run.event_ticker).where(
                Run.event_ticker.in_(tickers), (Run.created_at >= now - timedelta(hours=hours)) | Run.status.in_(("queued", "running")))))

    async def auto_research_cycle(self, now: datetime) -> None:
        s, state = self.app.state.settings, self.app.state
        started = await asyncio.to_thread(self._auto_started_today, now)
        self.status["auto_research_started_today"] = started
        if s.auto_research_max_per_day <= 0 or state.research_graph is None:
            return
        room = min(s.auto_research_max_per_day - started, s.max_concurrent_runs - state.active_runs)
        if room <= 0:
            return
        games = (await asyncio.to_thread(state.games.query, None, None, 400, False))["games"]
        soon = []
        for g in games:
            try:
                start = datetime.fromisoformat((g["starts_at"] or "").replace("Z", "+00:00"))
            except ValueError:
                continue  # no start time: the rule is about the soonest games, so it is skipped
            if now < start <= now + timedelta(hours=s.auto_research_hours_ahead):
                soon.append((start, -sum(float(o.get("volume") or 0) for o in g["outcomes"]), g["event_ticker"]))
        soon.sort()
        done = await asyncio.to_thread(self._recently_researched, [t for _, _, t in soon], now, s.auto_research_min_gap_hours) if soon else set()
        for _, _, ticker in [x for x in soon if x[2] not in done][:room]:
            try:
                await start_game_run(self.app, ticker, None, "auto")
                self.status["auto_research_started_today"] += 1
                log.info("Automatic research started for %s", ticker)
            except RunStartError as exc:
                log.warning("Automatic research for %s did not start: %s", ticker, exc.detail)
                if exc.status_code in (429, 503):
                    break  # no room or not configured: the next cycle tries again

    # ---- the loop -----------------------------------------------------------------------------------------

    async def cycle(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        try:
            await self.alert_cycle(now)
            await self.auto_research_cycle(now)
            self.status["last_error"] = None
        except Exception as exc:  # the loop must survive; the kind is shown in the app, the full text is in the log
            log.exception("A watcher cycle failed")
            self.status["last_error"] = type(exc).__name__
        self.status["last_cycle_at"] = now.isoformat()

    async def run_forever(self) -> None:
        interval = self.app.state.settings.monitor_interval_minutes * 60
        await asyncio.sleep(5)  # let the app finish starting
        while True:
            await self.cycle()
            await asyncio.sleep(interval)
