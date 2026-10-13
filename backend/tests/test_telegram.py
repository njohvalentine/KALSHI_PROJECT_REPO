"""The Telegram sender: the request, the error kinds, and that the token never leaks. No network."""

import asyncio
import logging

import httpx2
import pytest

from app import cli
from app.config import SettingsError, load_settings
from app.telegram import (
    TelegramBotBlocked, TelegramChatNotFound, TelegramError, TelegramNetworkError, TelegramNotifier, TelegramRateLimited,
    TelegramUnauthorized, find_chat_ids, hide_token_in_logs,
)

TOKEN = "123456789:AAExampleTokenWithEnoughCharacters_abc-123"
BASE = {"DATABASE_URL": "postgresql://x/y", "KALSHI_API_BASE": "https://k.test", "SESSION_SECRET": "s" * 40}


def notifier(handler):
    return TelegramNotifier(TOKEN, "987654", client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


def test_a_message_is_sent_as_plain_text_to_the_right_chat():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), request.read()
        return httpx2.Response(200, json={"ok": True, "result": {}})

    asyncio.run(notifier(handler).send("Worth a look: A vs B. Not a recommendation."))
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    import json
    body = json.loads(seen["body"])
    assert body == {"chat_id": "987654", "text": "Worth a look: A vs B. Not a recommendation.", "disable_web_page_preview": True}  # no parse_mode: markup is not read


def test_a_long_text_is_cut_to_what_telegram_accepts():
    sent = {}

    def handler(request):
        import json
        sent["text"] = json.loads(request.read())["text"]
        return httpx2.Response(200, json={"ok": True})

    asyncio.run(notifier(handler).send("x" * 9000))
    assert len(sent["text"]) == 4000


@pytest.mark.parametrize("status,description,kind", [
    (401, "Unauthorized", TelegramUnauthorized), (403, "Forbidden: bot was blocked by the user", TelegramBotBlocked),
    (400, "Bad Request: chat not found", TelegramChatNotFound), (429, "Too Many Requests: retry after 5", TelegramRateLimited),
    (500, "oops", TelegramError), (400, "Bad Request: message is too long", TelegramError),
])
def test_failures_have_a_kind_and_the_text_never_holds_the_token(status, description, kind):
    with pytest.raises(kind) as caught:
        asyncio.run(notifier(lambda r: httpx2.Response(status, json={"ok": False, "description": description})).send("hi"))
    assert type(caught.value) is kind and TOKEN not in str(caught.value) and "bot123" not in str(caught.value)


def test_an_unreachable_telegram_is_a_network_error_without_the_url():
    def handler(request):
        raise httpx2.ConnectError("could not connect to https://api.telegram.org/bot%s/sendMessage" % TOKEN, request=request)

    with pytest.raises(TelegramNetworkError) as caught:
        asyncio.run(notifier(handler).send("hi"))
    assert TOKEN not in str(caught.value) and caught.value.__cause__ is None and caught.value.__suppress_context__


def test_the_token_is_hidden_from_the_http_libraries_log_lines(caplog):
    hide_token_in_logs()
    hide_token_in_logs()  # twice is fine
    logger = logging.getLogger("httpx2")
    with caplog.at_level(logging.INFO, logger="httpx2"):
        logger.info('HTTP Request: %s %s "%s"', "POST", f"https://api.telegram.org/bot{TOKEN}/sendMessage", "HTTP/1.1 200 OK")
        logger.info(f"HTTP Request: POST https://api.telegram.org/bot{TOKEN}/getUpdates")
    assert TOKEN not in caplog.text and "bot<hidden>" in caplog.text


def test_alerts_need_both_telegram_values_and_they_must_look_right():
    assert load_settings(BASE).alerts_enabled is False  # off by default: alerts are recorded in the app only
    ok = load_settings(BASE | {"ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "-100123"})
    assert ok.alerts_enabled and ok.telegram_bot_token == TOKEN and ok.telegram_chat_id == "-100123"
    for bad, message in (
        ({"ALERTS_ENABLED": "true"}, "needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"),
        ({"ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN}, "needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"),
        ({"ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": "not-a-token", "TELEGRAM_CHAT_ID": "1"}, "does not look like a Telegram bot token"),
        ({"ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "abc"}, "TELEGRAM_CHAT_ID must be a number"),
    ):
        with pytest.raises(SettingsError, match=message) as caught:
            load_settings(BASE | bad)
        assert TOKEN not in str(caught.value)  # a setting error never prints the secret
    assert load_settings(BASE | {"TELEGRAM_BOT_TOKEN": "x"}).alerts_enabled is False  # values without ALERTS_ENABLED change nothing


def test_the_chat_id_helper_lists_the_chats_that_pressed_start():
    updates = {"ok": True, "result": [
        {"update_id": 1, "message": {"chat": {"id": 987654, "first_name": "Valentine", "type": "private"}, "text": "/start"}},
        {"update_id": 2, "message": {"chat": {"id": 987654, "first_name": "Valentine"}, "text": "hi"}},
        {"update_id": 3, "my_chat_member": {"chat": {"id": -1001, "title": "Alerts group"}}},
    ]}
    client = httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json=updates)))
    assert find_chat_ids(TOKEN, client) == [("987654", "Valentine"), ("-1001", "Alerts group")]
    empty = httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"ok": True, "result": []})))
    assert find_chat_ids(TOKEN, empty) == []
    with pytest.raises(TelegramUnauthorized):
        find_chat_ids(TOKEN, httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(401, json={"ok": False}))))


def test_the_helper_command_never_prints_the_token(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.main(["telegram-chat-id"]) == 2
    assert "TELEGRAM_BOT_TOKEN is not set" in capsys.readouterr().err
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    import app.telegram as telegram_module

    def boom(token, client=None):
        raise TelegramUnauthorized(f"Telegram answered HTTP 401 for bot{token}")  # even a careless message must not reach the screen
    monkeypatch.setattr(telegram_module, "find_chat_ids", boom)
    assert cli.main(["telegram-chat-id"]) == 1
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err and "TelegramUnauthorized" in out.err
    monkeypatch.setattr(telegram_module, "find_chat_ids", lambda token, client=None: [("42", "Me")])
    assert cli.main(["telegram-chat-id"]) == 0 and "TELEGRAM_CHAT_ID=42" in capsys.readouterr().out


from tests.conftest import EMAIL, PASSWORD, needs_db  # noqa: E402


@needs_db
def test_the_app_uses_telegram_only_when_alerts_are_enabled(make_client):
    with make_client() as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers={"X-Requested-With": "t"})
        assert client.app.state.notifier is None and client.get("/api/alerts").json()["monitor"]["channel"] == "app only"
    env = {"ALERTS_ENABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": "987654"}
    with make_client(**env) as client:
        client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers={"X-Requested-With": "t"})
        assert client.app.state.notifier is not None
        body = client.get("/api/alerts").json()
        assert body["monitor"]["channel"] == "Telegram" and TOKEN not in str(body)
