"""Sends alerts to a Telegram chat through Telegram's Bot API. The only code that makes an outgoing POST.

The bot token is a secret: it sits in the URL of every call, so it is kept in settings only, is never
logged (a log filter hides it from the HTTP library's own log lines) and never appears in an error
that reaches the page: a failure is reported by a kind of error, not by its text."""

import logging
import re

import httpx2

API = "https://api.telegram.org"
MAX_TEXT = 4000  # Telegram refuses messages over 4096 characters
TOKEN_IN_TEXT = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


class TelegramError(Exception):
    """A message could not be sent. The class name says what happened; the text never holds the token."""


class TelegramUnauthorized(TelegramError):
    """The token is wrong or the bot was deleted."""


class TelegramChatNotFound(TelegramError):
    """The chat id is wrong, or nobody pressed Start on the bot yet."""


class TelegramBotBlocked(TelegramError):
    """The person blocked the bot or removed it from the chat."""


class TelegramRateLimited(TelegramError):
    """Too many messages too fast."""


class TelegramNetworkError(TelegramError):
    """Telegram could not be reached."""


class _HideToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # The library passes the URL as an object, not a string, so the arguments cannot be masked one by one: the finished message is.
        try:
            message = record.getMessage()
        except Exception:  # a malformed log call (arguments that do not fit the text) must not raise from inside the filter; mask what is there
            message = str(record.msg)
        record.msg = TOKEN_IN_TEXT.sub("bot<hidden>", message)
        record.args = None
        return True


def hide_token_in_logs() -> None:
    """The HTTP libraries log every request line, URL included. Call once at start-up."""
    for name in ("httpx2", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _HideToken) for f in logger.filters):
            logger.addFilter(_HideToken())


def _error_for(status: int, description: str) -> TelegramError:
    text = (description or "").lower()
    if status == 401:
        return TelegramUnauthorized(f"Telegram answered HTTP {status}")
    if status == 403:
        return TelegramBotBlocked(f"Telegram answered HTTP {status}")
    if status == 429:
        return TelegramRateLimited(f"Telegram answered HTTP {status}")
    if status == 400 and "chat not found" in text:
        return TelegramChatNotFound(f"Telegram answered HTTP {status}")
    return TelegramError(f"Telegram answered HTTP {status}")


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx2.AsyncClient | None = None):
        self._token, self._chat_id, self._client = token, chat_id, client

    async def send(self, text: str) -> None:
        url = f"{API}/bot{self._token}/sendMessage"
        body = {"chat_id": self._chat_id, "text": text[:MAX_TEXT], "disable_web_page_preview": True}  # plain text: no markup is read
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body)
            else:
                async with httpx2.AsyncClient(timeout=httpx2.Timeout(10.0)) as client:
                    response = await client.post(url, json=body)
        except httpx2.HTTPError as exc:
            raise TelegramNetworkError(type(exc).__name__) from None  # from None: the original text holds the URL
        if response.status_code != 200:
            try:
                description = response.json().get("description", "")
            except ValueError:
                description = ""
            raise _error_for(response.status_code, description)


def find_chat_ids(token: str, client: httpx2.Client | None = None) -> list[tuple[str, str]]:
    """(chat id, name) of the chats that have written to the bot. The person presses Start on the bot first."""
    url = f"{API}/bot{token}/getUpdates"
    try:
        if client is not None:
            response = client.get(url, timeout=10)
        else:
            with httpx2.Client(timeout=10) as c:
                response = c.get(url)
    except httpx2.HTTPError as exc:
        raise TelegramNetworkError(type(exc).__name__) from None
    if response.status_code != 200:
        raise _error_for(response.status_code, "")
    found: dict[str, str] = {}
    for update in response.json().get("result", []):
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat") or {}
        if "id" in chat:
            found[str(chat["id"])] = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
    return list(found.items())
