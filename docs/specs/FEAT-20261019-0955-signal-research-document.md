# Spec: keep the signal research and its scripts

Branch `feature/sports-games-list` (base `master`). The user asked on 2026-10-19 to check an analysis made in another session and then said "your call, I just want better signals". Documentation and read-only scripts only: no change to the app, no database write, no OpenAI call.

- `docs/discussion/SIGNAL-RESEARCH-2026-10-19.md`: the findings, my check of each number against our database (done 2026-10-19: nine reproduce, the regression weight reproduces with the other session's own script and differs from a simple linear fit by the method, and "471 checks" are 53 games screened three times), what could not be checked, and the ranked ideas with the decision taken.
- `scripts/signal_analysis/`: the three scripts of the other session as they are (they read an export of the outcome records and, for the closing-line check, Kalshi's public candles, one request a second), a README with how to export the data and run them. The data exports themselves are not committed.
- Every statement from a paper is marked as not verified by us unless a source was read; the sources are listed as given.
