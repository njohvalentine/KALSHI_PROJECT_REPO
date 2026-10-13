import asyncio
from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseFunctionWebSearch, ResponseOutputMessage, ResponseUsage

from app.config import load_settings
from app.research.model import OpenAIResearchModel, ResearchModelError, segments_and_searches, usage_from
from app.research.schemas import Angle, GameInfo, Plan

SETTINGS = load_settings({
    "DATABASE_URL": "postgresql://u:p@db:5432/x",
    "KALSHI_API_BASE": "https://kalshi.test/trade-api/v2",
    "SESSION_SECRET": "s" * 40,
    "OPENAI_API_KEY": "sk-test",
})
MARKET = GameInfo(event_ticker="KX-1", title="Team A vs Team B", sub_title="Group stage", starts_at="2026-11-01T18:00:00+00:00", outcomes=["Team A wins", "Tie is the result", "Team B wins"])


def search_call(action):
    return ResponseFunctionWebSearch.model_validate({"id": "ws_1", "type": "web_search_call", "status": "completed", "action": action})


def message(text, annotations):
    return ResponseOutputMessage.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": annotations}],
    })


def usage(inp=1000, cached=200, out=300):
    return ResponseUsage.model_validate({
        "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out,
        "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 50},
    })


def cite(url, title, start, end):
    return {"type": "url_citation", "url": url, "title": title, "start_index": start, "end_index": end}


def test_parses_text_citations_searches_and_usage_from_sdk_objects():
    text = "- Star out injured (https://a.test). \n- Won last 5."
    response = SimpleNamespace(
        output=[
            search_call({"type": "search", "query": "team a injuries"}),
            search_call({"type": "open_page", "url": "https://a.test"}),  # opening a page is not a search
            search_call({"type": "search", "query": "team a form"}),
            message(text, [cite("https://a.test", "A news", 0, 25)]),
        ],
        usage=usage(),
    )
    segments, searches = segments_and_searches(response)
    assert searches == 2
    assert len(segments) == 1 and segments[0].text == text
    c = segments[0].citations[0]
    assert (c.url, c.title, c.start, c.end) == ("https://a.test", "A news", 0, 25)
    u = usage_from(response, "gpt-5.4", searches)
    assert (u.input_tokens, u.cached_tokens, u.output_tokens, u.search_calls, u.model) == (1000, 200, 300, 2, "gpt-5.4")


def test_non_url_annotations_are_ignored():
    response = SimpleNamespace(output=[ResponseOutputMessage.model_validate({
        "id": "m", "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": "x", "annotations": [
            {"type": "file_citation", "file_id": "f", "filename": "n", "index": 0}, cite("https://a.test", "t", 0, 1)]}],
    })], usage=usage())
    segments, _ = segments_and_searches(response)
    assert [c.url for c in segments[0].citations] == ["https://a.test"]


class FakeResponses:
    def __init__(self):
        self.calls = []

    async def create(self, **kw):
        self.calls.append(("create", kw))
        return SimpleNamespace(output=[search_call({"type": "search", "query": "q"}), message("- fact", [cite("https://a.test", "t", 0, 6)])], usage=usage())

    async def parse(self, **kw):
        self.calls.append(("parse", kw))
        return SimpleNamespace(output_parsed=Plan(angles=[Angle(name="Form", question="How has A played?")]), usage=usage(500, 0, 100))


def make_model():
    fake = SimpleNamespace(responses=FakeResponses())
    return OpenAIResearchModel(SETTINGS, client=fake), fake.responses


def test_research_call_uses_forced_search_caps_and_no_storage():
    model, responses = make_model()
    out = asyncio.run(model.research(MARKET, Angle(name="Form", question="How has A played?")))
    kind, kw = responses.calls[0]
    assert kind == "create" and kw["model"] == "gpt-5.4"
    assert kw["tool_choice"] == "required"          # the model may not skip searching
    assert kw["max_tool_calls"] == 3 and kw["max_output_tokens"] == 4000
    assert kw["store"] is False and kw["reasoning"] == {"effort": "low"}
    assert kw["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert "How has A played?" in kw["input"] and "Team A vs Team B" in kw["input"]
    assert "Scheduled start (exchange): 2026-11-01T18:00:00+00:00" in kw["input"] and "Team A wins; Tie is the result; Team B wins" in kw["input"]
    assert out.usage.search_calls == 1 and out.segments[0].citations[0].url == "https://a.test"


def test_the_game_description_has_no_price_field_so_agents_cannot_see_prices():
    assert not any("price" in f or "bid" in f or "ask" in f for f in GameInfo.__dataclass_fields__)
    model, responses = make_model()
    asyncio.run(model.plan(MARKET, 3))
    asyncio.run(model.research(MARKET, Angle(name="n", question="q")))
    for _, kw in responses.calls:
        assert "¢" not in kw["input"] and "price" not in kw["input"].lower()


def test_plan_call_uses_structured_output_and_the_planner_model():
    model, responses = make_model()
    plan, u = asyncio.run(model.plan(MARKET, max_angles=4))
    kind, kw = responses.calls[0]
    assert kind == "parse" and kw["model"] == "gpt-5.4-mini" and kw["text_format"] is Plan and kw["store"] is False
    assert "tools" not in kw  # the planner does not search
    assert "up to" not in kw["instructions"] and "4 research angles" in kw["instructions"]
    assert plan.angles[0].name == "Form" and u.model == "gpt-5.4-mini"


def test_api_errors_become_clear_model_errors_without_secrets():
    class Boom:
        async def create(self, **kw):
            raise RuntimeError("rate limit hit")

        async def parse(self, **kw):
            return SimpleNamespace(output_parsed=None, usage=usage())

    model = OpenAIResearchModel(SETTINGS, client=SimpleNamespace(responses=Boom()))
    with pytest.raises(ResearchModelError, match="Researcher call failed: RuntimeError$") as caught:
        asyncio.run(model.research(MARKET, Angle(name="n", question="q")))
    with pytest.raises(ResearchModelError, match="no usable plan"):
        asyncio.run(model.plan(MARKET, 3))


def test_provider_error_text_is_logged_not_put_in_the_error_that_reaches_the_run(caplog):
    class Boom:
        async def create(self, **kw):
            raise RuntimeError("Incorrect API key provided: sk-proj-****abcd")

        async def parse(self, **kw):
            raise RuntimeError("Incorrect API key provided: sk-proj-****abcd")

    model = OpenAIResearchModel(SETTINGS, client=SimpleNamespace(responses=Boom()))
    for call in (lambda: model.research(MARKET, Angle(name="n", question="q")), lambda: model.plan(MARKET, 3)):
        with caplog.at_level("WARNING"):
            with pytest.raises(ResearchModelError) as caught:
                asyncio.run(call())
        assert "sk-proj" not in str(caught.value) and "RuntimeError" in str(caught.value)
    assert "sk-proj-****abcd" in caplog.text


def test_the_start_line_is_left_out_when_the_start_is_unknown():
    from app.research.prompts import planner_input

    text = planner_input(GameInfo(event_ticker="E", title="A vs B", outcomes=["A wins"]), "2026-10-12")
    assert "Scheduled start" not in text and "Game: A vs B" in text


def test_game_from_a_kalshi_event_response():
    data = {
        "event": {"event_ticker": "KXEPL-26OCT12COVNEW", "title": "Coventry vs Newcastle", "sub_title": "COV vs NEW (Oct 12)"},
        "markets": [
            {"ticker": "A", "title": "Coventry wins", "yes_sub_title": "Coventry", "occurrence_datetime": "2026-10-12T22:00:00Z", "rules_primary": "If Coventry wins ..."},
            {"ticker": "B", "title": "Tie is the result", "yes_sub_title": "Tie", "occurrence_datetime": "2026-10-12T22:00:00Z"},
            {"ticker": "C", "title": "Newcastle wins", "yes_sub_title": "Newcastle", "occurrence_datetime": "2026-10-12T21:00:00Z"},
        ],
    }
    game = GameInfo.from_kalshi_event(data, starts_at="2026-10-12T16:30:00Z")
    assert game.event_ticker == "KXEPL-26OCT12COVNEW" and game.title == "Coventry vs Newcastle" and game.sub_title == "COV vs NEW (Oct 12)"
    assert game.outcomes == ["Coventry wins", "Tie is the result", "Newcastle wins"]
    assert game.starts_at == "2026-10-12T16:30:00Z" and game.rules == "If Coventry wins ..."  # the milestone's kickoff; first rules text
    # The markets' occurrence_datetime (settlement time) must never become the start.
    assert GameInfo.from_kalshi_event(data).starts_at is None
    nested = {"event": {"event_ticker": "E", "markets": [{"ticker": "X", "yes_sub_title": "Only"}]}}
    assert GameInfo.from_kalshi_event(nested).outcomes == ["Only"]  # markets nested inside the event also work
    for bad in ({"event": {}, "markets": [{"ticker": "x"}]}, {"event": {"event_ticker": "E"}, "markets": []}, {}):
        with pytest.raises(ValueError):
            GameInfo.from_kalshi_event(bad)


def test_an_account_without_credit_is_named_in_plain_words_and_other_errors_by_their_kind_only():
    from app.research.model import error_kind

    class NoCredit(Exception):
        code = "insufficient_quota"

    class Other(Exception):
        code = "something_else"

    assert error_kind(NoCredit("You have no credits remaining. sk-proj-secret")) == "NoCredit: the OpenAI account has no credit left"
    assert error_kind(Other("detail with sk-proj-secret")) == "Other"
    try:
        try:
            raise NoCredit("x")
        except NoCredit as inner:
            raise ResearchModelError("Forecaster call failed") from inner
    except ResearchModelError as wrapped:
        assert error_kind(wrapped) == "NoCredit: the OpenAI account has no credit left"  # the reason sits on the wrapped error
    assert "sk-proj" not in error_kind(NoCredit("sk-proj-secret"))


def test_a_run_with_no_credit_says_so_in_its_error(caplog):
    class NoCredit(Exception):
        code = "credit_balance_exhausted"

    class Boom:
        async def create(self, **kw):
            raise NoCredit("You have no credits remaining")

        async def parse(self, **kw):
            raise NoCredit("You have no credits remaining")

    model = OpenAIResearchModel(SETTINGS, client=SimpleNamespace(responses=Boom()))
    with pytest.raises(ResearchModelError, match="Planner call failed: NoCredit: the OpenAI account has no credit left"):
        asyncio.run(model.plan(MARKET, 3))
