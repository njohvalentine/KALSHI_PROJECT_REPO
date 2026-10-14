"""Operator commands. Run inside the backend: python -m app.cli <command>."""

import argparse
import getpass
import os
import sys

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session as DbSession

from app.kalshi_key_check import KeyCheckError, run_check, summarize
from app.models import Session, User
from app.security import MIN_PASSWORD_LENGTH, hash_password


class CliError(Exception):
    pass


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or any(c.isspace() for c in email):
        raise CliError(f"Not a valid email address: {email!r}")
    return email


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise CliError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def create_user(db: DbSession, email: str, password: str) -> None:
    email = normalize_email(email)
    check_password(password)
    if db.scalar(select(User).where(User.email == email)):
        raise CliError(f"A user with email {email} already exists")
    db.add(User(email=email, password_hash=hash_password(password)))
    db.commit()


def set_password(db: DbSession, email: str, password: str) -> None:
    email = normalize_email(email)
    check_password(password)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise CliError(f"No user with email {email}")
    user.password_hash = hash_password(password)
    user.failed_attempts = 0
    user.locked_until = None
    # Anyone already signed in (possibly with a stolen session) must sign in again.
    db.execute(delete(Session).where(Session.user_id == user.id))
    db.commit()


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise CliError("Passwords do not match")
    return first


def _records_command(args) -> int:
    from datetime import UTC, datetime

    from app.config import SettingsError, load_settings
    from app.kalshi import KalshiClient, KalshiError
    from app.research.records import format_report, resolve_records, score_records

    try:
        settings = load_settings(os.environ)
    except SettingsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    engine = create_engine(settings.sqlalchemy_url)
    if args.command == "score-records":
        since = None
        if args.since:
            try:
                since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
            except ValueError:
                print("Error: --since must look like 2026-10-13", file=sys.stderr)
                return 2
        series = {e.ticker: (e.sport, e.league) for e in settings.sports_series}
        print(format_report(score_records(engine, since, series, settings.min_supported_claims)))
        return 0
    client = KalshiClient(settings.kalshi_api_base)
    try:
        counts = resolve_records(engine, client, settings)
    except KalshiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Resolved: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items()))
    return 0


def _moment(text: str | None, name: str):
    from datetime import UTC, datetime

    if not text:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        raise CliError(f"{name} must look like 2026-10-13 or 2026-10-13T18:00") from None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _replay_command(args) -> int:
    import asyncio

    from app.config import SettingsError, load_settings
    from app.research.forecast import OpenAIForecastModel
    from app.research.model import openai_client
    from app.research.replay import estimate, format_summary, load_candidates, replay, split_test_set, summarize

    try:
        after, before, tune = _moment(args.created_after, "--created-after"), _moment(args.created_before, "--created-before"), _moment(args.tune_until, "--tune-until")
        if args.final and tune is None:
            raise CliError("--final needs --tune-until: it shows the games made after that moment")
        overrides = {k: v for k, v in vars(args).items() if k.isupper() and v is not None}
        settings = load_settings({**os.environ, **overrides})
    except (CliError, SettingsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    engine = create_engine(settings.sqlalchemy_url)
    items, held = split_test_set(load_candidates(engine, after, before), tune, args.final)
    if not items:
        print("No finished game with a saved forecast, claims and a result matches.")
        return 0
    label = ("final test set" if args.final else "tuning set" if tune else "all games") + (" (rules only)" if args.rules_only else "")
    if not args.rules_only:
        if not settings.research_enabled:
            print("Error: OPENAI_API_KEY is not set, so no model can be called. Use --rules-only to replay the flag rule alone.", file=sys.stderr)
            return 2
        calls, usd = estimate(items, settings)
        print(f"{len(items)} games x {settings.forecaster_count} forecasters = {calls} model calls with {settings.forecaster_model} "
              f"({settings.forecaster_reasoning_effort} effort), about {usd:.2f} USD at the default price per call (a rough estimate).")
        if not args.yes:
            print("Nothing was called. Run again with --yes to spend it.")
            return 0

    async def go():
        from app.checkpoint import open_checkpointer

        if args.rules_only:
            return await replay(engine, settings, items, rules_only=True, model_factory=None, load_game=None)
        pool, saver = await open_checkpointer(settings.database_url)
        client = openai_client(settings)

        async def load_game(run_id):
            found = await saver.aget_tuple({"configurable": {"thread_id": run_id}})
            return found.checkpoint["channel_values"].get("game") if found else None

        try:
            return await replay(engine, settings, items, rules_only=False,
                                model_factory=lambda day: OpenAIForecastModel(settings, client=client, today=day), load_game=load_game)
        finally:
            await pool.close()

    result = asyncio.run(go())
    result.held_back, result.held_back_is_early = held, bool(args.final)
    print(format_summary(summarize(result), label))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("create-user", "Create the sign-in account"), ("set-password", "Change a password and unlock the account")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("email")
        p.add_argument("--password-stdin", action="store_true", help="Read the password from stdin (for scripts)")
    sub.add_parser(
        "check-kalshi-key",
        help="Tell whether the Kalshi key works on demo or production (read-only, no orders)",
    )
    sub.add_parser("resolve-records", help="Fill in the results of recorded forecasts whose games are over (read-only on Kalshi)")
    sub.add_parser("telegram-chat-id", help="Print the chat id of the people who pressed Start on the Telegram bot (needs TELEGRAM_BOT_TOKEN)")
    score = sub.add_parser("score-records", help="Print how the recorded forecasts did against what happened")
    score.add_argument("--since", help="Only records made on or after this date (YYYY-MM-DD)")
    rp = sub.add_parser("replay-forecasts", help="Re-run the forecasting step and the flag rule on the evidence saved before each finished game")
    rp.add_argument("--created-after", help="Only runs made on or after this moment (YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    rp.add_argument("--created-before", help="Only runs made on or before this moment")
    rp.add_argument("--tune-until", help="Use only runs made up to this moment; later games are held back as the test set")
    rp.add_argument("--final", action="store_true", help="With --tune-until: show only the held-back test set (do this once, after the settings are fixed)")
    rp.add_argument("--rules-only", action="store_true", help="No model call: replay only the flag rule on the original forecasts")
    rp.add_argument("--yes", action="store_true", help="Spend money on model calls (without it only the estimate is printed)")
    for flag, setting in (("--forecaster-count", "FORECASTER_COUNT"), ("--forecaster-model", "FORECASTER_MODEL"), ("--forecaster-effort", "FORECASTER_REASONING_EFFORT"),
                          ("--edge-min", "EDGE_MIN"), ("--min-supported-claims", "MIN_SUPPORTED_CLAIMS"), ("--min-research-shift", "MIN_RESEARCH_SHIFT"),
                          ("--edge-plausible-max", "EDGE_PLAUSIBLE_MAX"), ("--min-ask-size", "MIN_ASK_SIZE")):
        rp.add_argument(flag, dest=setting, metavar=setting, help=f"Replay with this value of {setting} instead of the current setting")
    args = parser.parse_args(argv)

    if args.command == "replay-forecasts":
        return _replay_command(args)

    if args.command == "check-kalshi-key":
        try:
            results, warnings = run_check(os.environ)
        except KeyCheckError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        for r in results:
            print(f"{r.name}: {r.status}" + (f" ({r.detail})" if r.detail else ""))
        print(summarize(results))
        return 0

    if args.command == "telegram-chat-id":
        from app.telegram import TelegramError, find_chat_ids

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            print("Error: TELEGRAM_BOT_TOKEN is not set (put it in .env, then run this inside the backend container)", file=sys.stderr)
            return 2
        try:
            chats = find_chat_ids(token)
        except TelegramError as exc:
            print(f"Error: {type(exc).__name__}", file=sys.stderr)  # never the text: it could hold the token
            return 1
        if not chats:
            print("No chat has written to the bot yet. Open the bot in Telegram, press Start, then run this again.")
            return 1
        for chat_id, name in chats:
            print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")
        return 0

    if args.command in ("resolve-records", "score-records"):
        return _records_command(args)

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql://"):
        print("DATABASE_URL must be set and start with postgresql://", file=sys.stderr)
        return 2
    engine = create_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        password = _read_password(args.password_stdin)
        with DbSession(engine) as db:
            (create_user if args.command == "create-user" else set_password)(db, args.email, password)
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
