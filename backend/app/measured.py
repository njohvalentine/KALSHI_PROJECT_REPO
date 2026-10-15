"""Which sports have scored results. A sport with fewer scored games than MEASURED_MIN_GAMES is "not yet measured"."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import OutcomeRecord


def scored_games_in(db: DbSession) -> dict[str, int]:
    """Games with a result and a forecast made before the start, per sport (records without a sport are not counted)."""
    rows = db.execute(
        select(OutcomeRecord.sport, func.count(func.distinct(OutcomeRecord.event_ticker)))
        .where(OutcomeRecord.sport.is_not(None), OutcomeRecord.resolved_yes.is_not(None), OutcomeRecord.before_start.is_(True))
        .group_by(OutcomeRecord.sport)
    ).all()
    return {sport: n for sport, n in rows}


def scored_games_by_sport(engine) -> dict[str, int]:
    with DbSession(engine) as db:
        return scored_games_in(db)
