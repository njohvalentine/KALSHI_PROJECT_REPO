import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import create_engine, text

from app.config import Settings, load_settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fails here, before serving anything, if required settings are bad.
        app.state.settings = settings or load_settings(os.environ)
        app.state.engine = create_engine(app.state.settings.sqlalchemy_url, pool_pre_ping=True)
        yield
        app.state.engine.dispose()

    app = FastAPI(title="Valentine backend", lifespan=lifespan)

    @app.get("/health")
    def health(response: Response):
        try:
            with app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "ok", "db": True}
        except Exception as exc:  # report, do not hide, why the db is not reachable
            log.error("Health check: database not reachable: %s", exc)
            response.status_code = 503
            return {"status": "degraded", "db": False}

    return app


app = create_app()
