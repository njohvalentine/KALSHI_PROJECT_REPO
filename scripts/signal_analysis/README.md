# Signal analysis scripts (read-only)

Three scripts that ask: does our forecast carry information that Kalshi's price does not? They write nothing to the database and place nothing. They were written in another working session on 2026-10-19 and are kept as they are.

## Export the data

From the project folder, with the database up:

```
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\copy (select * from outcome_records) to stdout with csv header" > records.csv
```

Keep `records.csv` out of the repository (it is a copy of the database).

## Run

```
cd backend
uv run python ../scripts/signal_analysis/signal_check.py records.csv
```

Prints: the Brier scores, whether our forecast adds anything beyond the price (a logistic regression, with the interval from resampling whole games), a leave-one-game-out blend, who is right when we disagree with the price, calibration, how far we sit from the price, the cost of crossing the spread, the lean by kind of market, and whether the research moves us the right way.

Closing line value (did the price later move toward our number?), two steps, one request a second so it does not disturb other jobs:

```
cd backend
uv run python ../scripts/signal_analysis/clv_fetch.py records.csv closing.json
uv run python ../scripts/signal_analysis/clv_analyse.py records.csv closing.json
```

`clv_fetch.py` and `clv_analyse.py` use the app's own Kalshi client (public GET only). They need the VPN. Run them from `backend` so that `import app...` works.

## Read the numbers with care

62 finished games is a small sample. The first scripts' intervals are by game, because the markets of one game are not independent.
