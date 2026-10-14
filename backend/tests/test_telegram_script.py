"""The Telegram hello script: what it says, and that it never shows the token or the chat id. A fake sender; nothing is sent."""

import importlib.util
from pathlib import Path

import pytest

from app.telegram import (
    TelegramBotBlocked, TelegramChatNotFound, TelegramError, TelegramNetworkError, TelegramRateLimited, TelegramUnauthorized,
)

PATH = Path(__file__).resolve().parents[2] / "scripts" / "telegram_hello.py"
spec = importlib.util.spec_from_file_location("telegram_hello", PATH)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

TOKEN = "987654321:ZZdistinctiveTOKENvalue_1234567890"
CHAT = "5550001112223"
ENV = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}


def sender(error=None):
    sent = []

    async def send(text):
        sent.append(text)
        if error:
            raise error

    return send, sent


def test_missing_values_stop_it_with_their_names_and_nothing_is_sent(capsys):
    send, sent = sender()
    assert script.main({"TELEGRAM_CHAT_ID": CHAT}, send) == 2
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN is NOT set" in out and "Put TELEGRAM_BOT_TOKEN in .env" in out and sent == [] and CHAT not in out


def test_it_sends_the_hello_message_and_says_so(capsys):
    send, sent = sender()
    assert script.main(ENV, send) == 0
    assert sent == [script.MESSAGE] and "Hello from the Forecast desk" in sent[0] and "Nothing was bet or ordered" in sent[0]
    assert "Sent: check Telegram." in capsys.readouterr().out


@pytest.mark.parametrize("error,words", [
    (TelegramUnauthorized("x"), "token is wrong"), (TelegramChatNotFound("x"), "pressed Start"), (TelegramBotBlocked("x"), "blocked the bot"),
    (TelegramRateLimited("x"), "too many messages"), (TelegramNetworkError("x"), "VPN"), (TelegramError("x"), "refused the message"),
])
def test_each_failure_is_named_in_plain_words(capsys, error, words):
    send, sent = sender(error)
    assert script.main(ENV, send) == 1
    assert words in capsys.readouterr().out


def test_the_token_and_the_chat_id_are_never_printed_and_no_logging_is_set_up(capsys):
    for error in (None, TelegramUnauthorized("HTTP 401 for https://api.telegram.org/bot" + TOKEN), TelegramChatNotFound(CHAT)):
        script.main(ENV, sender(error)[0])
    out = capsys.readouterr().out
    assert TOKEN not in out and CHAT not in out
    source = PATH.read_text()
    assert "logging" not in source.replace("sets up no logging", "") and "basicConfig" not in source
