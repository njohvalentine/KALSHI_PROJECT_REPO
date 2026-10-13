import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import create_engine, text

from app.auth import router as auth_router
from app.checkpoint import open_checkpointer
from app.games import GamesService
from app.games import router as games_router
from app.config import Settings, load_settings
from app.kalshi import KalshiClient
from app.markets import router as markets_router
from app.research.graph import build_graph
from app.research.check import OpenAIClaimJudge
from app.research.forecast import OpenAIForecastModel
from app.research.model import OpenAIResearchModel
from app.research.runner import mark_stale_runs_failed
from app.runs import router as runs_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


def create_app(settings: Settings | None = None, research_model=None, judge=None, forecaster=None, fetch_options=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fails here, before serving anything, if required settings are bad.
        app.state.settings = settings or load_settings(os.environ)
        app.state.engine = create_engine(app.state.settings.sqlalchemy_url, pool_pre_ping=True)
        app.state.kalshi = KalshiClient(app.state.settings.kalshi_api_base)
        app.state.games = GamesService(lambda: app.state.kalshi, app.state.settings)
        # Fails here if the database is unreachable, instead of starting half-working.
        app.state.checkpoint_pool, app.state.checkpointer = await open_checkpointer(
            app.state.settings.database_url
        )
        # Research is on when a model is available: the real one needs OPENAI_API_KEY (settings log
        # the off state); tests pass a fake one.
        model = research_model or (OpenAIResearchModel(app.state.settings) if app.state.settings.research_enabled else None)
        app.state.research_graph = (
            build_graph(model, app.state.settings, app.state.checkpointer) if model else None
        )
        # The checker and the forecasters need the same key as research; tests pass fakes (or none, which
        # leaves the stages after research off, and the run says so).
        key = app.state.settings.research_enabled
        app.state.judge = judge or (OpenAIClaimJudge(app.state.settings) if key else None)
        app.state.forecaster = forecaster or (OpenAIForecastModel(app.state.settings) if key else None)
        app.state.fetch_options = fetch_options or {}
        app.state.active_runs = 0
        app.state.tasks = set()
        await asyncio.to_thread(mark_stale_runs_failed, app.state.engine)
        yield
        # Shutdown: give running runs a moment to finish, then cancel them (they record themselves as failed).
        pending = list(app.state.tasks)
        if pending:
            await asyncio.wait(pending, timeout=10)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        await app.state.checkpoint_pool.close()
        app.state.kalshi.close()
        app.state.engine.dispose()

    # The interactive API docs are off: they would publish the full endpoint list to anyone.
    app = FastAPI(title="Valentine backend", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(auth_router)
    app.include_router(markets_router)
    app.include_router(games_router)
    app.include_router(runs_router)

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
