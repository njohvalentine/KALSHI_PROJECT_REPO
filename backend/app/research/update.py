"""A lineup update of a researched game (FEAT-20261022-0956): one fixed research angle per sport instead of the planner, and the earlier checked evidence carried over
into the new run instead of being paid for again.

The question asks who is MISSING or a surprise, not for the whole lineup: a researcher writes at most 10 lines, one fact per line, and a lineup is 22 names."""

import copy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import ClaimCheck, Run, SourcePage
from app.research.schemas import Angle

_ANGLES = {
    "Soccer": Angle(name="Lineups and late team news", question=(
        "Which regular starters of either team are NOT in the confirmed starting lineup, or are out, injured, suspended or doubtful, and what surprise selections or "
        "formation changes were announced? Give the time each source was published. If the starting lineups are not published yet, say so in one line.")),
    "Baseball": Angle(name="Probable pitchers and lineup cards", question=(
        "Who are the confirmed starting pitchers for this game, and which regular position players are missing from the posted lineup cards or on the injured list? "
        "Give the time each source was published.")),
    "Basketball": Angle(name="Starters and injury report", question=(
        "Who are the confirmed starters for this game, and what is the injury report status (out, doubtful, questionable, resting) of each team's main players? "
        "Give the time each source was published.")),
    "Tennis": Angle(name="Withdrawals and late match news", question=(
        "Has either player withdrawn, retired from a recent match, taken a medical timeout, or been reported injured, and when is the match scheduled on the order of play? "
        "Give the time each source was published.")),
}
_DEFAULT = Angle(name="Late team news", question=(
    "What is the latest team or player news for this game (who is out, injured, suspended or rested, and any confirmed lineup or starters)? Give the time each source was published."))


def update_angles(sport: str | None) -> list[Angle]:
    return [_ANGLES.get(sport or "", _DEFAULT)]


def _age(hours: float) -> str:
    return "less than an hour" if hours < 1 else f"{round(hours)} hours"


def carry_over(engine, old_run_id: str, new_run_id: str, new_count: int, now: datetime) -> list[dict]:
    """Copies the checked evidence of the earlier run into the update run: its pages (with their saved text and status, so nothing is fetched again) and its claim checks
    (so nothing is judged again; the finding index moves up by `new_count`, because the new findings come first). Returns the earlier findings, labelled
    "Earlier research (N hours ago): <angle>", for the update run's result. The earlier run itself is not changed."""
    with DbSession(engine) as db:
        old = db.get(Run, old_run_id)
        findings = copy.deepcopy((old.result or {}).get("findings", []))
        label = f"Earlier research ({_age(max((now - (old.finished_at or old.created_at)).total_seconds() / 3600, 0))} ago): "
        for f in findings:
            f["angle"] = label + f["angle"]
            f["carried_from"] = old_run_id
        for p in db.scalars(select(SourcePage).where(SourcePage.run_id == old_run_id).order_by(SourcePage.id)).all():
            db.add(SourcePage(run_id=new_run_id, url=p.url, title=p.title, retrieved_at=p.retrieved_at, content_hash=p.content_hash, content=p.content, fetch_status=p.fetch_status,
                              fetch_method=p.fetch_method, final_url=p.final_url, http_status=p.http_status, fetched_at=p.fetched_at, fetch_detail=p.fetch_detail,
                              page_text=p.page_text, page_text_hash=p.page_text_hash))
        for c in db.scalars(select(ClaimCheck).where(ClaimCheck.run_id == old_run_id).order_by(ClaimCheck.finding_index, ClaimCheck.claim_index)).all():
            db.add(ClaimCheck(run_id=new_run_id, finding_index=c.finding_index + new_count, claim_index=c.claim_index, source_url=c.source_url, verdict=c.verdict, reason=c.reason, model=c.model))
        db.commit()
    return findings
