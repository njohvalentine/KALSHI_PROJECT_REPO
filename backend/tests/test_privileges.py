"""Least privilege (FEAT-20261024): which tools each model role may use, checked before a call and on its answer. No network."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.research import privileges
from app.research.check import OpenAIClaimJudge, Verdicts
from app.research.forecast import OpenAIForecastModel
from app.research.model import OpenAIResearchModel, ResearchModelError
from app.research.privileges import ALLOWED_TOOLS, PrivilegeViolation, check_response, request
from app.research.schemas import Angle
from tests.test_forecast import CLAIMS, FRAMINGS, GAME, SETTINGS as FORECAST_SETTINGS, answer
from tests.test_research_model import MARKET, SETTINGS, FakeResponses, message, search_call, usage

ROLES = ("planner", "researcher", "judge", "forecaster")
WEB = {"type": "web_search", "search_context_size": "medium"}


def item(kind):
    return SimpleNamespace(type=kind, name="send_report", arguments='{"secret": "do-not-log-this"}')


def test_only_the_researcher_may_use_a_tool_and_only_the_hosted_search():
    assert ALLOWED_TOOLS == {"planner": (), "researcher": ("web_search",), "judge": (), "forecaster": ()}


@pytest.mark.parametrize("role", ROLES)
def test_a_request_with_a_tool_outside_the_list_is_refused(role):
    for tool in ({"type": "function", "name": "place_order"}, {"type": "mcp", "server_label": "x"}, {"type": "code_interpreter"}):
        with pytest.raises(PrivilegeViolation, match=role):
            request(role, model="m", tools=[tool])


def test_a_request_inside_the_list_passes_unchanged():
    assert request("judge", model="m", store=False) == {"model": "m", "store": False}
    assert request("researcher", model="m", tools=[WEB])["tools"] == [WEB]
    with pytest.raises(PrivilegeViolation):
        request("judge", model="m", tools=[WEB])  # the judge may not search


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("kind", ["function_call", "mcp_call", "shell_call", "code_interpreter_call", "computer_call", "file_search_call",
                                  "custom_tool_call", "local_shell_call", "image_generation_call", "a_type_added_by_a_later_sdk"])
def test_an_answer_that_contains_a_tool_call_is_refused(role, kind):
    with pytest.raises(PrivilegeViolation, match=f"{role}.*{kind}"):
        check_response(role, SimpleNamespace(output=[item("message"), item(kind)]))


def test_an_answer_of_messages_and_reasoning_passes_and_a_search_passes_for_the_researcher_only():
    plain = SimpleNamespace(output=[item("reasoning"), item("message")])
    for role in ROLES:
        check_response(role, plain)
    searched = SimpleNamespace(output=[item("web_search_call"), item("message")])
    check_response("researcher", searched)
    for role in ("planner", "judge", "forecaster"):
        with pytest.raises(PrivilegeViolation, match="web_search_call"):
            check_response(role, searched)


def test_a_refusal_is_logged_with_the_role_and_the_kind_and_never_the_content(caplog):
    with caplog.at_level(logging.WARNING), pytest.raises(PrivilegeViolation) as caught:
        check_response("judge", SimpleNamespace(output=[item("function_call")]))
    assert "judge" in caplog.text and "function_call" in caplog.text
    assert "do-not-log-this" not in caplog.text + str(caught.value) and "send_report" not in caplog.text + str(caught.value)


def test_an_unknown_role_is_an_error_not_a_free_pass():
    with pytest.raises(KeyError):
        check_response("intern", SimpleNamespace(output=[]))
    with pytest.raises(KeyError):
        request("intern", model="m")


# The four real places that call the model: each turns a tool call in the answer into a model error and returns no data.

def test_the_researcher_and_the_planner_refuse_a_tool_call_in_the_answer():
    class Bad(FakeResponses):
        async def create(self, **kw):
            return SimpleNamespace(output=[item("function_call"), message("- fact", [])], usage=usage())

        async def parse(self, **kw):
            return SimpleNamespace(output=[item("mcp_call")], output_parsed=None, usage=usage())

    model = OpenAIResearchModel(SETTINGS, client=SimpleNamespace(responses=Bad()))
    with pytest.raises(ResearchModelError, match="Researcher call failed: PrivilegeViolation"):
        asyncio.run(model.research(MARKET, Angle(name="n", question="q")))
    with pytest.raises(ResearchModelError, match="Planner call failed: PrivilegeViolation"):
        asyncio.run(model.plan(MARKET, 3))


def test_the_judge_refuses_a_tool_call_in_the_answer():
    class Responses:
        async def parse(self, **kw):
            return SimpleNamespace(output=[item("function_call")], output_parsed=Verdicts(verdicts=[]), usage=usage())

    judge = OpenAIClaimJudge(SETTINGS, client=SimpleNamespace(responses=Responses()))
    with pytest.raises(ResearchModelError, match="Claim check call failed: PrivilegeViolation"):
        asyncio.run(judge.judge("A vs B", "https://a.test", None, "text", False, ["c1"]))


def test_the_forecaster_refuses_a_tool_call_in_the_answer():
    class Responses:
        async def parse(self, **kw):
            return SimpleNamespace(output=[item("shell_call")], output_parsed=answer(0.4, 0.3, 0.3), usage=usage())

    model = OpenAIForecastModel(FORECAST_SETTINGS, client=SimpleNamespace(responses=Responses()))
    with pytest.raises(ResearchModelError, match="Forecaster call failed: PrivilegeViolation"):
        asyncio.run(model.forecast(GAME, CLAIMS, FRAMINGS[0]))


def test_a_researcher_call_still_sends_exactly_the_hosted_search_and_no_other_role_sends_a_tool():
    responses = FakeResponses()
    model = OpenAIResearchModel(SETTINGS, client=SimpleNamespace(responses=responses))
    asyncio.run(model.research(MARKET, Angle(name="n", question="q")))
    asyncio.run(model.plan(MARKET, 3))
    assert responses.calls[0][1]["tools"] == [WEB] and "tools" not in responses.calls[1][1]
    assert privileges.__doc__
