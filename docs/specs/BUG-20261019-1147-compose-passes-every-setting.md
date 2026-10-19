# Spec: the compose file must pass every setting, and the defaults must live in one place

Branch `feature/sports-games-list` (base `master`). Found on 2026-10-19 by the confirming run of FEAT-20261019-0959.

## What is wrong (verified)

- `docker-compose.yml` lists, one by one, the settings handed to the backend container (`environment:`). `config.py` reads 78 settings; the compose file passes 66. Twelve are missing: `RESEARCH_MAX_PER_DAY`, `SCREEN_HOURS_AHEAD`, `SCREEN_MIN_CREDITS_LEFT`, `SCREEN_MAX_LEAGUES`, `ORDER_PAUSE_DAY_LOSS_USD`, `ORDER_PAUSE_TOTAL_LOSS_USD`, `ORDER_LOSS_SINCE`, `ORDER_MAX_GAME_COST_USD`, `ORDER_MAX_OPEN_COST_USD` (all added over the last days) and `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `SESSION_TTL_HOURS` (older). **A value written in `.env` for any of them never reaches the container, and nothing says so.** I checked: none of the nine new ones is in the running container. In particular the stop rules and risk limits of `docs/RISK-FRAMEWORK.md` could not be switched on from `.env`, and the daily research limit could not be changed.
- Each passed setting repeats its default (`${MAX_RESEARCHERS:-4}`), a second copy of the default in `config.py`. They have drifted once already: `MAX_RESEARCHERS` is 3 in the code (FEAT-20261019-0959) and 4 in the compose file, which wins, so the saving of that item did not appear (the confirming run researched four angles and cost 0.459 dollars against the 0.434 average).
- Why it went unseen: the backend tests build the settings from a dictionary, never through the compose file, and the browser tests do not set these values.

## Design

- **Pass every tunable setting through, with no default in the compose file.** In `environment:`, each tunable becomes the pass-through form `NAME:` (no value): Compose then takes it from the shell or from `.env` when it is set, and passes nothing when it is not, so the code default applies. The defaults then live in `config.py` only. Shell overrides keep working as before (`ALERTS_ENABLED=false docker compose up -d`).
- **Add the twelve missing settings.** Kept as they are: `DATABASE_URL` (built from the `POSTGRES_*` values), `KALSHI_API_BASE` and `SESSION_SECRET` (required; they fail loudly at start when missing), and the frontend part.
- **A test so it cannot happen again** (`tests/test_compose_settings.py`, reading both files): every name `config.py` reads is in the backend `environment:` of the compose file, and none of them has a `:-default` there (except the derived `DATABASE_URL`).
- **A check that pass-through works as I describe**, before relying on it: `docker compose config` with a name unset and set (shown in the close-out), and the running backend's log after the change (`MAX_RESEARCHERS` 3, "Research is limited to 5 games").
- Docs: the run guide's settings section says that every setting in `.env.example` reaches the backend and that the defaults are in `config.py`.

## Not done

No change to the values the user has in `.env` (not read or changed); no `env_file` (it would not let a shell override win, which the way we start the stack for tests depends on); no change to the frontend container.

## Tests

The new compose test (it must fail on the current file: 12 missing, 66 with defaults); the existing settings tests; the confirming run again after the fix: the plan has three angles and no odds angle, and the cost is lower than 0.434 (about 0.35 dollars, counted in the daily limit, only with the user's yes).

## Checks to state at close

Lateral spread: all 78 settings compared (done: 12 missing, one differing default); the frontend and database services read no settings from this list. Causal depth: the symptom (a default that did not take) had two causes, the copy of the default in the compose file and the missing names, and a third, no test crossing the compose file and `config.py`; each is handled.
