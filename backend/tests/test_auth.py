import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.cli import CliError, create_user, set_password
from tests.conftest import EMAIL, PASSWORD, needs_db

pytestmark = needs_db

H = {"X-Requested-With": "test"}


def login(client, email=EMAIL, password=PASSWORD, headers=H):
    return client.post("/auth/login", json={"email": email, "password": password}, headers=headers)


def test_login_sets_safe_cookie_and_me_works(make_client):
    with make_client() as client:
        r = login(client)
        assert r.status_code == 200 and r.json() == {"email": EMAIL}
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
        assert client.get("/auth/me").json() == {"email": EMAIL}


def test_secure_flag_set_when_enabled(make_client):
    with make_client(SESSION_COOKIE_SECURE="true") as client:
        assert "secure" in login(client).headers["set-cookie"].lower()


def test_email_is_case_insensitive(make_client):
    with make_client() as client:
        assert login(client, email="  Owner@Example.COM ").status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(make_client):
    with make_client() as client:
        wrong = login(client, password="not the password")
        unknown = login(client, email="nobody@example.com")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}
        assert "set-cookie" not in wrong.headers


def test_lockout_after_repeated_failures_then_unlock(make_client):
    with make_client() as client:
        for _ in range(3):
            assert login(client, password="bad bad bad bad").status_code == 401
        # Locked now: even the right password is refused, with the same generic answer.
        r = login(client)
        assert r.status_code == 401 and r.json() == {"detail": "Invalid email or password"}
        with make_client.engine.begin() as conn:
            conn.execute(text("UPDATE users SET locked_until = now() - interval '1 minute'"))
        assert login(client).status_code == 200


def test_successful_login_resets_failed_attempts(make_client):
    with make_client() as client:
        login(client, password="bad bad bad bad")
        login(client, password="bad bad bad bad")
        assert login(client).status_code == 200
        for _ in range(2):  # two more failures must not lock (counter was reset)
            login(client, password="bad bad bad bad")
        assert login(client).status_code == 200


def test_login_requires_requested_with_header(make_client):
    with make_client() as client:
        assert login(client, headers={}).status_code == 403
        login(client)
        assert client.post("/auth/logout").status_code == 403


def test_expired_session_is_rejected(make_client):
    with make_client() as client:
        login(client)
        with make_client.engine.begin() as conn:
            conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
        assert client.get("/auth/me").status_code == 401


def test_logout_ends_the_session(make_client):
    with make_client() as client:
        login(client)
        assert client.post("/auth/logout", headers=H).status_code == 200
        assert client.get("/auth/me").status_code == 401
        with make_client.engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0


def test_forged_cookie_is_rejected(make_client):
    with make_client() as client:
        client.cookies.set("session", "x" * 43)
        assert client.get("/auth/me").status_code == 401


def test_every_route_except_health_and_login_needs_a_session(make_client):
    open_paths = {"/health", "/auth/login"}
    with make_client() as client:
        # The schema lists every route no matter how routers are wrapped inside FastAPI.
        paths = client.app.openapi()["paths"]
        assert "/auth/me" in paths and "/auth/logout" in paths, "test is not seeing the real routes"
        checked = 0
        for path, operations in paths.items():
            if path in open_paths:
                continue
            for method in operations:
                r = client.request(method.upper(), path.replace("{ticker}", "x"), headers=H)
                assert r.status_code == 401, f"{method.upper()} {path} is not protected"
                checked += 1
        assert checked >= 2


def test_secrets_never_stored_or_logged(make_client, caplog):
    caplog.set_level(logging.DEBUG)
    with make_client() as client:
        r = login(client)
        token = r.cookies.get("session") or client.cookies.get("session")
        with make_client.engine.connect() as conn:
            pw_hash = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
            tok_hash = conn.execute(text("SELECT token_hash FROM sessions")).scalar_one()
        assert pw_hash.startswith("$argon2") and PASSWORD not in pw_hash
        assert token and tok_hash != token and token not in tok_hash
    assert PASSWORD not in caplog.text and token not in caplog.text


def test_cli_rules(make_client):
    from sqlalchemy.orm import Session as DbSession

    with DbSession(make_client.engine) as db:
        with pytest.raises(CliError, match="already exists"):
            create_user(db, EMAIL.upper(), PASSWORD)
        with pytest.raises(CliError, match="at least 12"):
            create_user(db, "new@example.com", "short")
        with pytest.raises(CliError, match="valid email"):
            create_user(db, "not-an-email", PASSWORD)
        with pytest.raises(CliError, match="No user"):
            set_password(db, "ghost@example.com", PASSWORD)
        set_password(db, EMAIL, "a brand new password")
    with make_client() as client:
        assert login(client, password=PASSWORD).status_code == 401
        assert login(client, password="a brand new password").status_code == 200


def test_password_change_signs_out_existing_sessions(make_client):
    from sqlalchemy.orm import Session as DbSession

    with make_client() as client:
        assert login(client).status_code == 200
        assert client.get("/auth/me").status_code == 200
        with DbSession(make_client.engine) as db:
            set_password(db, EMAIL, "a brand new password")
        assert client.get("/auth/me").status_code == 401
        with make_client.engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0


def test_parallel_wrong_logins_cannot_beat_the_lockout(make_client, caplog):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    caplog.set_level(logging.WARNING, logger="app.auth")
    workers = 12
    barrier = Barrier(workers)
    clients = [make_client() for _ in range(workers)]  # separate apps and connections

    def attack(client):
        with client:
            barrier.wait()
            return login(client, password="bad bad bad bad").status_code

    with ThreadPoolExecutor(max_workers=workers) as pool:
        codes = list(pool.map(attack, clients))
    assert set(codes) == {401}
    with make_client.engine.connect() as conn:
        failed, locked = conn.execute(text("SELECT failed_attempts, locked_until FROM users")).one()
    assert locked is not None and locked > datetime.now(UTC) + timedelta(minutes=10)
    assert failed == 0
    assert caplog.text.count("Account locked") == 1  # lost updates would lock more than once or never
