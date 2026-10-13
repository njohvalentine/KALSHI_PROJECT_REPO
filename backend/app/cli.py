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
        print(format_report(score_records(engine, since)))
        return 0
    client = KalshiClient(settings.kalshi_api_base)
    try:
        counts = resolve_records(engine, client, settings)
    except KalshiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Resolved: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items()))
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
    score = sub.add_parser("score-records", help="Print how the recorded forecasts did against what happened")
    score.add_argument("--since", help="Only records made on or after this date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

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
