# Spec: sign-in can exhaust the server (BUG-20261012-1019)

Branch: `master` (base: `master`). Found by a second automated security review of the sign-in code. The review gave only the category (denial of service in `backend/app/auth.py`), so this spec records what was verified in the code.

## Verified causes (read `backend/app/auth.py`, `login()`)

1. **Row lock held during hashing.** The fix for BUG-20261012-0959 reads the user with `FOR UPDATE` and then runs the Argon2 check, so the lock and a database connection are held for the whole hash. Parallel logins for one email queue behind each other; every waiter holds a connection from the pool (default 5 plus 10 overflow), so a flood can use them all and make every other endpoint wait.
2. **No cap on concurrent hashing.** `/auth/login` is open to anyone and every request, including unknown emails, runs an Argon2 hash (CPU and memory heavy). Nothing limits how many run at once, and each takes a worker thread, so a flood can fill the thread pool.
3. **Lockout can be triggered by anyone who knows the email** (accepted, see below).

## Fix

- Read the user's id and hash first, end that transaction (releasing the connection), run the Argon2 check with **no database lock and no connection held**, then take `FOR UPDATE` only for the short state change (check lock, count failure or clear counter, create the session). If the password changed in between (hash no longer matches what was checked), refuse.
- Allow at most **4 sign-in checks at the same time** in this process (a bounded semaphore, a tuning constant with a safe default). Extra requests get `429` with `Retry-After` at once, instead of queueing and holding resources.
- Order of effects: everything that can only fail the caller stays cheap; nothing waits on a lock for long.

## What this does and does not change

- The lockout still counts failures exactly (the state change is serialized by the short row lock), and a correct password is refused once the account is locked. Guesses already being hashed when the lock engages are bounded by the cap (4), so an attacker gets about N + 4 guesses per lockout window, not unlimited.
- **Accepted limits (documented, not fixed):** (a) anyone who knows the email can lock the owner out for `LOGIN_LOCKOUT_MINUTES` by sending wrong passwords; existing sessions keep working and the operator can unlock with `set-password`; (b) a flood of login requests can make real logins return 429 while it lasts, but it can no longer slow the rest of the app. Fixing both properly needs per-IP limits at a reverse proxy, which is outside Milestone 1 (HTTPS and a proxy come with real deployment).

## Lateral check

Other unauthenticated endpoints: only `/health` (one cheap query) and `/auth/login`. Authenticated endpoints sit behind `require_user`, a single indexed lookup. No other expensive unauthenticated work found.

## Tests

- While the password is being checked, no row lock is held on the user and no database connection is checked out (verified with a `FOR UPDATE NOWAIT` from a second connection and the pool's checked-out count).
- With all 4 slots taken, a login gets `429` with `Retry-After`, while `/health` and an authenticated endpoint still answer.
- If the password is changed during the check, the login is refused.
- The earlier tests (exact lockout, parallel guesses locking exactly once, generic errors) still pass; the parallel test now accepts `429` as well as `401` for the extra requests.
