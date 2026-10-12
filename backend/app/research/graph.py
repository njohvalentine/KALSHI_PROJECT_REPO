"""The research graph: a lead agent plans angles, researchers look into them in parallel."""

import logging
import operator
from dataclasses import asdict
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.research.model import ResearchModel, ResearchModelError
from app.research.schemas import MarketInfo

log = logging.getLogger("app.research")


class EmptyPlanError(ResearchModelError):
    """The planner returned no research angles."""


class ResearchState(TypedDict, total=False):
    market: dict  # MarketInfo as a plain dict (checkpoints must hold plain data)
    angles: list[dict]
    cut_angles: int  # how many planned angles were dropped to stay within the cap
    usages: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]


def build_graph(model: ResearchModel, settings: Settings, checkpointer=None):
    async def plan(state: ResearchState) -> dict:
        market = MarketInfo(**state["market"])
        plan_, usage = await model.plan(market, settings.max_researchers)
        angles = plan_.angles
        if not angles:
            raise EmptyPlanError("The planner returned no research angles")
        cut = max(len(angles) - settings.max_researchers, 0)
        if cut:
            log.warning(
                "Planner proposed %d angles; keeping %d (MAX_RESEARCHERS), dropping %d",
                len(angles), settings.max_researchers, cut,
            )
        return {
            "angles": [a.model_dump() for a in angles[: settings.max_researchers]],
            "cut_angles": cut,
            "usages": [asdict(usage)],
        }

    builder = StateGraph(ResearchState)
    builder.add_node("plan", plan)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", END)
    return builder.compile(checkpointer=checkpointer)
