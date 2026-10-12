"""Single-user sign-in: login, logout, and the dependency that protects endpoints."""

import logging
import threading
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.db import get_db
from app.models import Session, User
from app.security import DUMMY_HASH, new_session_token, token_hash, verify_password

log = logging.getLogger("app.auth")

COOKIE_NAME = "session"
GENERIC_LOGIN_ERROR = "Invalid email or password"

router = APIRouter(prefix="/auth", tags=["auth"])


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_requested_with(x_requested_with: str | None = Header(default=None)) -> None:
    """Basic guard against cross-site form posts, on top of SameSite=Lax.
    Browsers do not let another site add a custom header to a request without our consent."""
    if not x_requested_with:
        raise HTTPException(status_code=403, detail="Missing X-Requested-With header")


def now() -> datetime:
    return datetime.now(UTC)


def require_user(
    request: Request,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    row = db.scalar(
        select(Session).where(Session.token_hash == token_hash(settings.session_secret, token))
    )
    if row is None or row.expires_at <= now():
        raise HTTPException(status_code=401, detail="Not signed in")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


class LoginBody(BaseModel):
    email: str
    password: str


# At most this many password checks run at once in this process. Hashing is CPU and memory heavy
# and /auth/login is open to anyone, so extra requests are refused at once (429) instead of
# queueing. A tuning constant with a safe default (CLAUDE.md Module 4).
MAX_CONCURRENT_LOGINS = 4
_login_slots = threading.BoundedSemaphore(MAX_CONCURRENT_LOGINS)


@router.post("/login", dependencies=[Depends(require_requested_with)])
def login(
    body: LoginBody,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not _login_slots.acquire(blocking=False):
        log.warning("Sign-in refused: %d password checks already running", MAX_CONCURRENT_LOGINS)
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts at once. Try again in a moment.",
            headers={"Retry-After": "1"},
        )
    try:
        return _login(body, response, db, settings)
    finally:
        _login_slots.release()


def _login(body: LoginBody, response: Response, db: DbSession, settings: Settings):
    email = body.email.strip().lower()

    # 1. Read what is needed, then end the transaction so no connection is held while hashing.
    found = db.execute(select(User.id, User.password_hash).where(User.email == email)).first()
    db.rollback()

    # 2. Check the password with no database lock and no connection held. One check always runs,
    #    so timing is the same for unknown emails and locked accounts.
    password_ok = verify_password(body.password, found.password_hash if found else DUMMY_HASH)

    if found is None:
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    # 3. Short critical section. FOR UPDATE makes parallel logins for one account take turns, so
    #    each sees the committed failure count and lock state (simultaneous guesses cannot
    #    overwrite each other's counts).
    user = db.scalar(select(User).where(User.id == found.id).with_for_update())
    current = now()
    locked = user is None or (user.locked_until is not None and user.locked_until > current)
    # A password changed while we were hashing must not let the old password in.
    changed = user is not None and user.password_hash != found.password_hash

    if user is None or locked or changed or not password_ok:
        if user is not None and not locked and not changed and not password_ok:
            user.failed_attempts += 1
            if user.failed_attempts >= settings.login_max_attempts:
                user.locked_until = current + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_attempts = 0
                log.warning("Account locked after repeated failed logins (user id %s)", user.id)
            db.commit()
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    user.failed_attempts = 0
    user.locked_until = None
    db.execute(delete(Session).where(Session.user_id == user.id, Session.expires_at <= current))
    token = new_session_token()
    db.add(
        Session(
            user_id=user.id,
            token_hash=token_hash(settings.session_secret, token),
            expires_at=current + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return {"email": user.email}


@router.post("/logout", dependencies=[Depends(require_requested_with), Depends(require_user)])
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(Session).where(Session.token_hash == token_hash(settings.session_secret, token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(require_user)):
    return {"email": user.email}
