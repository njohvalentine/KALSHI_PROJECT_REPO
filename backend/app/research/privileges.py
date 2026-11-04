"""Least privilege: which tools each model role may use, checked in code before a call and on its answer.

Judge, planner and forecasters have no tools; the researcher has only OpenAI's hosted read-only web search. The answer
check is an allow-list of item types, so a type added to the SDK later is refused until someone decides about it.
There is deliberately no setting that turns this off. A refusal is logged with the role and the item type only, never its content."""

import logging

log = logging.getLogger("app.research.privileges")

ALLOWED_TOOLS: dict[str, tuple[str, ...]] = {"planner": (), "researcher": ("web_search",), "judge": (), "forecaster": ()}  # the plain-AI baseline is a forecaster
_ANSWER_ITEMS = ("message", "reasoning")
_ANSWER_ITEMS_FOR = {"researcher": _ANSWER_ITEMS + ("web_search_call",)}


class PrivilegeViolation(Exception):
    """A model call asked for, or answered with, a tool its role may not use."""


def request(role: str, **kwargs) -> dict:
    """The arguments of a model call, after checking that every tool in them is allowed for `role` (KeyError for an unknown role)."""
    allowed = ALLOWED_TOOLS[role]
    for tool in kwargs.get("tools") or []:
        if tool.get("type") not in allowed:
            log.warning("Tool request refused for %s: %s", role, tool.get("type"))
            raise PrivilegeViolation(f"{role} may not use the tool {tool.get('type')}")
    return kwargs


def check_response(role: str, response) -> None:
    """Refuses an answer that contains anything but the item types this role may produce."""
    ALLOWED_TOOLS[role]  # an unknown role is a KeyError, never a free pass
    allowed = _ANSWER_ITEMS_FOR.get(role, _ANSWER_ITEMS)
    for output_item in response.output:
        if output_item.type not in allowed:
            log.warning("Answer refused for %s: item type %s", role, output_item.type)
            raise PrivilegeViolation(f"{role} answered with {output_item.type}, which it may not use")
