"""The alerts history and the state of the watcher, for the Opportunities page."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth import require_user
from app.db import get_db
from app.models import Alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(require_user)])


@router.get("")
def recent_alerts(request: Request, db: Annotated[DbSession, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=100)] = 20):
    settings, monitor = request.app.state.settings, request.app.state.monitor
    alerts = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(limit)).all()
    return {
        "alerts": [
            {"id": a.id, "created_at": a.created_at.isoformat(), "kind": a.kind, "event_ticker": a.event_ticker, "run_id": a.run_id,
             "title": a.title, "text": a.text, "status": a.status, "detail": a.detail}
            for a in alerts
        ],
        "monitor": {
            "enabled": settings.monitor_enabled, "interval_minutes": settings.monitor_interval_minutes,
            "channel": "app only" if request.app.state.notifier is None else "chat",
            "last_cycle_at": monitor.status["last_cycle_at"], "last_error": monitor.status["last_error"],
            "auto_research_cap": settings.auto_research_max_per_day,
            "auto_research_started_today": monitor.status["auto_research_started_today"],
        },
    }
