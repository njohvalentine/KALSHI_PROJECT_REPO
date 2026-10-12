"""Password hashing and session tokens."""

import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()  # Argon2
# Verified against when an email is unknown, so response time does not reveal which emails exist.
DUMMY_HASH = _password_hash.hash("not-a-real-password")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(secret: str, token: str) -> str:
    """Keyed hash of a session token. The database stores this, never the token."""
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
