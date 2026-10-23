"""The research graph: a lead agent plans angles, researchers look into them in parallel."""

import logging
import operator
from dataclasses import asdict
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import Settings
from app.research.claims import build_claims
from app.research.model import ResearchModel, ResearchModelError
from app.research.schemas import Angle, GameInfo, is_market_angle

log = logging.getLogger("app.research")


class EmptyPlanError(ResearchModelError):
    """The planner returned no research angles."""


class ResearchState(TypedDict, total=False):
    game: dict  # GameInfo as a plain dict (checkpoints must hold plain data)
    angles: list[dict]
    cut_angles: int  # how many planned angles were dropped to stay within the cap
    dropped_odds_angles: int  # how many angles about betting odds were dropped (nothing uses their result)
    fixed_angles: list[dict]  # an update run: these angles are researched and the planner is not called
    findings: Annotated[list[dict], operator.add]  # one entry per researcher that produced findings
    usages: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]


def build_graph(model: ResearchModel, settings: Settings, checkpointer=None):
    async def plan(state: ResearchState) -> dict:
        if state.get("fixed_angles"):  # a lineup update: the angle is fixed, no planner call, no planner cost
            return {"angles": state["fixed_angles"][: settings.max_researchers], "cut_angles": 0, "dropped_odds_angles": 0, "usages": []}
        game = GameInfo(**state["game"])
        plan_, usage = await model.plan(game, settings.max_researchers)
        # Nothing uses research about betting odds (the checker never lets it go forward, the forecasters ignore odds, the app reads the
        # bookmakers itself), so an angle about it is dropped before it is paid for, even if the planner plans one against its instructions.
        odds = [a for a in plan_.angles if is_market_angle(a.kind, a.name)]
        angles = [a for a in plan_.angles if not is_market_angle(a.kind, a.name)]
        if odds:
            log.info("Planner proposed %d angle(s) about betting odds (%s); dropped, nothing uses them", len(odds), ", ".join(a.name for a in odds))
        if not angles:
            raise EmptyPlanError("The planner returned no research angles" + (" (only angles about betting odds, which are not researched)" if odds else ""))
        cut = max(len(angles) - settings.max_researchers, 0)
        if cut:
            log.warning(
                "Planner proposed %d angles; keeping %d (MAX_RESEARCHERS), dropping %d",
                len(angles), settings.max_researchers, cut,
            )
        return {
            "angles": [a.model_dump() for a in angles[: settings.max_researchers]],
            "cut_angles": cut,
            "dropped_odds_angles": len(odds),
            "usages": [asdict(usage)],
        }

    def fan_out(state: ResearchState) -> list[Send]:
        # One researcher per angle. Each runs in parallel with its own input; results are merged by
        # the list reducers in ResearchState, and the graph ends once every researcher is done.
        return [Send("research", {"game": state["game"], "angle": a}) for a in state["angles"]]

    async def research(work: dict) -> dict:
        game = GameInfo(**work["game"])
        angle = Angle(**work["angle"])
        try:
            output = await model.research(game, angle)
        except ResearchModelError as exc:
            log.warning("Researcher for angle %r failed: %s", angle.name, exc)
            return {"errors": [{"angle": angle.name, "error": str(exc)}]}
        except Exception as exc:  # a bug in one researcher must not lose the others; it is logged in full
            log.exception("Researcher for angle %r crashed", angle.name)
            return {"errors": [{"angle": angle.name, "error": type(exc).__name__}]}
        usages = [asdict(output.usage)]  # the call was paid for even if its answer is unusable
        claims, bad = build_claims(output.segments)
        if not claims:
            return {"usages": usages, "errors": [{"angle": angle.name, "error": "The answer contained no findings"}]}
        return {
            "usages": usages,
            "findings": [{
                "angle": angle.name,
                "question": angle.question,
                "kind": angle.kind,
                "claims": [c.as_dict() for c in claims],
                "ignored_citations": bad,
            }],
        }

    builder = StateGraph(ResearchState)
    builder.add_node("plan", plan)
    builder.add_node("research", research)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", fan_out, ["research"])
    builder.add_edge("research", END)
    return builder.compile(checkpointer=checkpointer)
