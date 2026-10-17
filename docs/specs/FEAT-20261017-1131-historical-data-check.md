# Spec: what historical data exists and what it costs (client priority I)

Branch `feature/sports-games-list` (base `master`). The client asked on 2026-10-16 to "expand historical testing and demonstrate whether our forecasts can outperform Kalshi and bookmaker probabilities". The user approved on 2026-10-17 a first step that only checks what exists and what it costs, and reports the options before anything is bought.

Documentation and read-only checks only: no code, no dependency, no purchase. The result is `docs/discussion/HISTORICAL-DATA-2026-10-17.md`. The checks: Kalshi's public history endpoints (read-only, no login), The Odds API's documentation and one call of our free key to the history endpoint (a call that a free plan refuses at no credit cost). Decision the report asks for: whether the client wants to pay for one month of the bookmaker history, and whether to run the free Kalshi-only test.
