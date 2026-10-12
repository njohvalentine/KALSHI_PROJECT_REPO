# Spec: sign-in security review findings (BUG-20261012-0959, BUG-20261012-1000)

Branch: `master` (base: `master`). Both found by an automated security review of commit 9977d3f (FEAT-20261012-0953).

## BUG-20261012-0959, login failure counter race

**Verified root cause (read `backend/app/auth.py`, `login()`):** the user row is read with a plain SELECT, `failed_attempts` is increased in Python, and written back at commit. Two requests that read the row before either commits both see the same old value and both write old+1, so one failure is lost. An attacker sending many guesses in parallel therefore gets more than `LOGIN_MAX_ATTEMPTS` tries, and the lockout can be delayed or missed.

**Fix:** read the user row with `SELECT ... FOR UPDATE` (SQLAlchemy `with_for_update()`). Concurrent logins for the same account then wait for each other, and after the wait each sees the committed counter and lock state. The row lock is held during the password check (tens of milliseconds), which is acceptable for a single-user tool. Unknown emails have no row, so nothing is locked for them.

**Lateral check:** the only read-modify-write counter in the code base is `failed_attempts`. Session creation and deletion are single statements. Nothing else found.

**Known limit, not fixed here:** guesses against emails that do not exist cannot be counted per account, so there is no throttle on them. A per-IP limit would need a new component and is out of scope; the real account is still protected by the lockout, and the password policy (12+ characters, Argon2) keeps guessing impractical.

**Test:** twelve simultaneous wrong-password logins on separate connections against the real Postgres; afterwards the account must be locked, the counter reset, and exactly one "Account locked" event logged. The test must fail when the row lock is removed (checked by hand once).

## BUG-20261012-1000, sessions survive a password change

**Verified root cause (`backend/app/cli.py`, `set_password()`):** it updates the hash and clears the lockout but never touches the `sessions` table, so a session created before the change stays valid until it expires (up to `SESSION_TTL_HOURS`, default 12).

**Fix:** `set_password` deletes every session of that user in the same transaction as the password update.

**Lateral check:** `create_user` makes a new user with no sessions. No other code path changes credentials. Login already removes only the user's expired sessions, which is intended.

**Test:** sign in, change the password through `set_password`, then `GET /auth/me` with the old cookie must return 401, and the sessions table must hold no rows for that user.
