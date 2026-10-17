# Spec: an explicit NO BET answer for every game (client priority H)

Branch `feature/sports-games-list` (base `master`). The client wrote on 2026-10-16: "I want the system to recommend NO BET whenever the research does not establish a sufficiently strong opportunity". Approved by the user on 2026-10-17 as the third item.

## What is there now (read in the code)

- A market is either flagged "worth a look" or "Not flagged" with reasons (`research/compare.py`). `opportunities.py: build_row` makes one row per game from a fresh comparison (flagged count, risks, measured, stale); the run page, the Opportunities page and the alerts (`monitor.py: alert_text`) each word the outcome their own way. Nothing says "no bet", and a flagged game looks like a go even though no finished-game scores show that the flag works (the Dashboard says "no sign of an edge yet").

## Design

- **One rule in one place:** a new `backend/app/verdict.py` with a pure function `verdict(flagged, stale, unavailable, measured, track)` that returns `{kind, label, text}`, used by the Opportunities rows, the run detail and the alerts, so the three can never disagree. `track` is the track record, from the same numbers and the same rule as the Dashboard's message (too few games / ahead of Kalshi by at least 0.005 / no sign of an edge), read through a small helper `track_kind` that is cached for 60 seconds (the scores change only when a game finishes).
- **The three answers:**
  - `no_bet`, label **NO BET**: no market passed the tests, or the forecast is older than 12 hours, or there is no forecast or no price to compare with. The text gives the reason in one sentence ("no market passed all the tests", "the forecast is old: research the game again if you are interested", ...).
  - `look_caution`, label **Worth a look**: at least one market passed, but the track record does not show that the flag works yet (not "ahead") or the sport is not yet measured. The text: "Worth a look, but NO BET is the default: our forecasts have not beaten the Kalshi price on finished games (see the Dashboard)" and/or "this sport has not been measured: the flag has not been tested here".
  - `look`, label **Worth a look**: a market passed, the sport is measured and the track record is "ahead". The text says it is not a recommendation.
  - The word BET never appears without NO in front of it; nothing is ever called a recommendation to bet.
- **Where it shows:**
  - Opportunities: each row's status badge is the label ("NO BET" in place of "Not flagged"); a `look_caution` row has the caution sentence under the bet.
  - Run page: the "At a glance" box starts with the verdict as its headline ("NO BET" with its reason, or "Worth a look" with its caution), then the flagged markets as now. It uses the verdict of the stored forecast (prices at the time of the run, which the page already says).
  - Alerts: "Worth a look" and "Starting soon" alerts carry the caution sentence of a `look_caution` game (replacing today's separate "not yet tested" sentence, whose wording is kept inside it); "No longer worth a look" ends with "NO BET."
  - The Games page keeps its per-outcome "Worth a look" badge (it is about one market's forecast).
- API: `/api/opportunities` rows and `GET /api/runs/{id}` get a `verdict` field.
- Documented in the run guide and in HOW-IT-WORKS (section 5.5).

## Not done

No change to when a market is flagged (the six tests stay as they are); no betting amount and no "BET" answer; no per-sport track record (the Dashboard's overall one is used, and the sport rule uses the existing measured flag).

## Tests

Backend: every branch of `verdict` (and a check that no text contains "BET" without "NO" before it); `track_kind` for too few games, ahead and no edge, and that it is cached; the Opportunities row and the run detail carry the verdict; the alert texts for the three cases and for "no longer flagged"; the old not-yet-tested alert wording still appears inside the caution. Frontend: lint, build; the browser tests that look for "Not flagged" on Opportunities now look for "NO BET"; the run page test checks the headline of the At a glance box.

## Checks to state at close

Lateral spread: all three places that word the outcome (Opportunities, run page, alerts) call the same function; I search the frontend and the backend for the old "Not flagged" and "not been tested" wording and state what is left on purpose (the per-market reasons in the run table). Causal depth: the request has two parts, say NO BET when the research is weak, and do not let a flag read as a go while the scores show no edge; the second part is why a flagged game gets the caution until the track record turns.
