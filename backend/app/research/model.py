"""The model calls. One interface, one real implementation over the OpenAI Responses API.

Parameters were checked against the installed openai SDK (3.29.0). They have not been exercised
against the live service yet (no key in the build environment); see the spec, section 9."""

import logging
from datetime import UTC, datetime
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings
from app.research.prompts import PLANNER_INSTRUCTIONS, RESEARCHER_INSTRUCTIONS, planner_input, researcher_input
from app.research.schemas import Angle, Citation, GameInfo, Plan, ResearchOutput, TextSegment, Usage

log = logging.getLogger("app.research")


class ResearchModelError(Exception):
    """A model call failed or returned something unusable."""


class ResearchModel(Protocol):
    async def plan(self, game: GameInfo, max_angles: int) -> tuple[Plan, Usage]: ...

    async def research(self, game: GameInfo, angle: Angle) -> ResearchOutput: ...


NO_CREDIT_CODES = ("insufficient_quota", "credit_balance_exhausted")


def error_kind(exc: Exception) -> str:
    """The kind of a failed OpenAI call for people to read: the error class, and a plain reason for the one case
    that needs an action (no credit left). The message of the error itself is never included."""
    cause = exc.__cause__ if isinstance(exc, ResearchModelError) and exc.__cause__ is not None else exc  # the wrapped OpenAI error
    if getattr(cause, "code", None) in NO_CREDIT_CODES:
        return f"{type(cause).__name__}: the OpenAI account has no credit left"
    return type(exc).__name__


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def usage_from(response, model: str, search_calls: int = 0) -> Usage:
    u = getattr(response, "usage", None)
    if u is None:
        raise ResearchModelError("The model response has no usage information")
    return Usage(
        model=model,
        input_tokens=u.input_tokens,
        cached_tokens=u.input_tokens_details.cached_tokens,
        output_tokens=u.output_tokens,
        search_calls=search_calls,
    )


def segments_and_searches(response) -> tuple[list[TextSegment], int]:
    """Pulls the answer text with its citations, and the number of web searches, from a response."""
    segments: list[TextSegment] = []
    searches = 0
    for item in response.output:
        if item.type == "web_search_call":
            if item.action.type == "search":
                searches += 1
        elif item.type == "message":
            for part in item.content:
                if part.type != "output_text":
                    continue
                citations = [
                    Citation(url=a.url, title=a.title, start=a.start_index, end=a.end_index)
                    for a in part.annotations
                    if a.type == "url_citation"
                ]
                segments.append(TextSegment(text=part.text, citations=citations))
    return segments, searches


def openai_client(settings: Settings) -> AsyncOpenAI:
    """The one place an OpenAI client is built (with LangSmith tracing when it is switched on)."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    if settings.langsmith_tracing:
        from langsmith.wrappers import wrap_openai

        client = wrap_openai(client)
    return client


class OpenAIResearchModel:
    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None):
        self._s = settings
        self._client = client or openai_client(settings)

    async def plan(self, game: GameInfo, max_angles: int) -> tuple[Plan, Usage]:
        today = _today()
        try:
            response = await self._client.responses.parse(
                model=self._s.planner_model,
                instructions=PLANNER_INSTRUCTIONS.format(max_angles=max_angles, today=today),
                input=planner_input(game, today),
                text_format=Plan,
                reasoning={"effort": self._s.research_reasoning_effort},
                max_output_tokens=self._s.researcher_max_output_tokens,
                store=False,
            )
        except Exception as exc:
            log.warning("Planner call failed: %s: %s", type(exc).__name__, exc)  # the full text stays in the log
            raise ResearchModelError(f"Planner call failed: {error_kind(exc)}") from exc
        if response.output_parsed is None:
            raise ResearchModelError("The planner returned no usable plan")
        return response.output_parsed, usage_from(response, self._s.planner_model)

    async def research(self, game: GameInfo, angle: Angle) -> ResearchOutput:
        today = _today()
        try:
            response = await self._client.responses.create(
                model=self._s.researcher_model,
                instructions=RESEARCHER_INSTRUCTIONS.format(today=today),
                input=researcher_input(game, angle, today),
                tools=[{"type": "web_search", "search_context_size": "medium"}],
                tool_choice="required",  # with "auto" the model may skip searching
                max_tool_calls=self._s.max_searches_per_researcher,
                reasoning={"effort": self._s.research_reasoning_effort},
                max_output_tokens=self._s.researcher_max_output_tokens,
                store=False,
            )
        except Exception as exc:
            log.warning("Researcher call failed: %s: %s", type(exc).__name__, exc)
            raise ResearchModelError(f"Researcher call failed: {error_kind(exc)}") from exc
        segments, searches = segments_and_searches(response)
        return ResearchOutput(segments=segments, usage=usage_from(response, self._s.researcher_model, searches))
