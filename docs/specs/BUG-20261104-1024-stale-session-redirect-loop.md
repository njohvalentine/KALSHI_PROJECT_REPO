# Spec: redirect loop on the sign-in page with a stale session cookie (BUG-20261104-1024)

Branch: `master` (checked out). One commit with its test.

## What is broken

A browser that still holds a `session` cookie that the backend no longer accepts (the database was reset, or `set-password` signed out all sessions of the account) shows `ERR_TOO_MANY_REDIRECTS` on `/login` and on every page until its cookies are deleted. Seen on 4 Nov: the cookie of a removed test copy reached the next copy on the same address.

## Verified root cause

Two redirects point at each other. `frontend/proxy.ts` sends `/login` to `/games` when a cookie named `session` exists (it only checks that the cookie exists), and `frontend/lib/session.ts` (`verifySession`) sends a 401 from the backend to `/login`. The proxy's own comment says it does not prove the session is valid; the login path trusts it anyway.

## Lateral spread (same cause, other places)

Nine places redirect to `/login` on a 401 and would hit the same loop: `lib/session.ts` and eight client components (`run-view`, `order-actions`, `update-button`, `analyze-button`, `prepare-order`, `ticket`, and the sign-out button, which goes to the sign-in page either way). They share one cause, so they get **one** fix at the point that creates the loop, not nine.

## Fix

Remove the cookie-based `/login` redirect from `proxy.ts` (it still sends a visitor with no cookie from any other page to `/login`). The login page, a server component, does the real check instead: it asks the backend (`/auth/me`, through `backendFetch`). A valid session goes to `/games` as before (so a signed-in person who opens `/login` still lands in the app); anything else shows the sign-in form. If the backend cannot be reached the form is shown too, and the cause is logged on the server (no silent fallback: signing in then says the server is unreachable). A stale cookie is not deleted: it is replaced when the person signs in.

## Checks

Causal depth: the loop needs both redirects; the other half (a 401 goes to `/login`) is right and stays. The only other reason a cookie can be stale is expiry in the backend, which ends in the same state and is covered by the same fix.

## Test

Browser test (Playwright, `frontend/e2e/auth.spec.ts`): (1) with a made-up `session` cookie, opening `/games` ends on `/login` with the form visible and no redirect error; (2) with a real signed-in session, opening `/login` still ends on `/games`; (3) the existing sign-in and sign-out tests still pass. Run against the rebuilt Docker frontend with the `e2e` test account. The guide's troubleshooting row for this is removed once the fix is in.
