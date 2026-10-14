"""Sends one hello message to the Telegram chat the alerts go to, to check that delivery works.

Run it from your own terminal (the values are read from the environment, nothing is written):

    cd backend && set -a; source ../.env; set +a; uv run python ../scripts/telegram_hello.py

It uses the same sender as the watcher, so a pass proves the real path. It prints whether each value is set, never the
values themselves, and it sets up no logging: the HTTP library's request line holds the bot token in the address."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.telegram import (  # noqa: E402
    TelegramBotBlocked, TelegramChatNotFound, TelegramError, TelegramNetworkError, TelegramNotifier, TelegramRateLimited, TelegramUnauthorized,
)

MESSAGE = ("Hello from the Forecast desk. This is a test message: if you can read it, alerts to this chat work. "
           "Nothing was bet or ordered.")

WHY = (
    (TelegramUnauthorized, "The bot token is wrong, or the bot was deleted. Copy the token from @BotFather again into TELEGRAM_BOT_TOKEN."),
    (TelegramChatNotFound, "The chat id is wrong, or you have not pressed Start on your bot. Open the bot in Telegram, press Start, and check TELEGRAM_CHAT_ID."),
    (TelegramBotBlocked, "You blocked the bot, or removed it from the chat. Unblock it or add it again."),
    (TelegramRateLimited, "Telegram says too many messages were sent too fast. Wait a minute and run the script again."),
    (TelegramNetworkError, "Telegram could not be reached. Check the internet connection and the VPN."),
)


def main(env=None, sender=None) -> int:
    env = os.environ if env is None else env
    token, chat_id = env.get("TELEGRAM_BOT_TOKEN", "").strip(), env.get("TELEGRAM_CHAT_ID", "").strip()
    print(f"TELEGRAM_BOT_TOKEN is {'set' if token else 'NOT set'}; TELEGRAM_CHAT_ID is {'set' if chat_id else 'NOT set'}.")
    if not token or not chat_id:
        missing = " and ".join(name for name, value in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)) if not value)
        print(f"Nothing was sent. Put {missing} in .env and load it (see the top of this file).")
        return 2
    send = sender or TelegramNotifier(token, chat_id).send
    try:
        asyncio.run(send(MESSAGE))
    except TelegramError as exc:
        print("Not sent. " + next((why for kind, why in WHY if isinstance(exc, kind)), f"Telegram refused the message ({type(exc).__name__})."))
        return 1
    print("Sent: check Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
