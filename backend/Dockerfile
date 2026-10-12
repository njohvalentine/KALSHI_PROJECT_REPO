FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

WORKDIR /srv
RUN useradd --system --create-home appuser

# Dependencies first, so this layer is cached until the lock file changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
USER appuser

# Applies pending database migrations, then starts the server. A failed migration stops the start.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
