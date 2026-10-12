# Spec: markets page waits about a minute when Kalshi is unreachable (BUG-20261012-1029)

Branch: `master` (base: `master`).

## Verified cause

Measured on the compose stack with Kalshi unreachable: the markets page returned its error message after 63.6 seconds. In `backend/app/kalshi.py` the default client uses one 15-second timeout for every phase and tries 4 times with 0.5/1/2-second waits, so a failing connection costs roughly 4 x 15 + 3.5 seconds. That budget suits a background job, not a page a person is waiting on.

## Fix

- Default timeout: 3 seconds to connect, 10 seconds to read a response (a healthy Kalshi answers in well under a second; an unreachable host should fail fast).
- Default attempts: 3 instead of 4. Worst case for an unreachable host becomes about 3 x 3 + 1.5 = 10.5 seconds.
- Both stay constructor arguments, so a later background job can ask for more patience explicitly.

## Lateral check

Only `KalshiClient` calls out to Kalshi. The web app's own calls to the backend use the default fetch behavior, which waits as long as the backend does, so the backend limit is the one that matters.

## Test

The default client has connect timeout 3 and read timeout 10, and gives up after 3 tries (existing retry tests keep passing with the explicit attempt counts they already use).
