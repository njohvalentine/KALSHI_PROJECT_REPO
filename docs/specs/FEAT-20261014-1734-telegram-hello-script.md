# Spec: a script that sends a hello message to test Telegram

Branch `feature/sports-games-list` (base `master`). For approval; nothing is written yet. Asked for by the user on 2026-10-14: "create a script for testing the telegram bot, save it in scripts folder and send a simple hello message".

## Why

Telegram was switched on on 2026-10-14 and no alert has arrived because the watcher only sends when something happens (a flagged game starts within an hour, a market moves 8 cents or more). Nobody knows yet whether delivery works. The only way to find out today is to send a message on purpose.

## Design

- **File:** `scripts/telegram_hello.py` (a new folder at the top of the repository; it did not exist). Not part of the Docker image; run from the host with the backend's own environment, so no new dependency:
  `cd backend && set -a; source ../.env; set +a; uv run python ../scripts/telegram_hello.py`
  (sourcing `.env` in the person's own shell only puts the values in that process; nothing is written).
- **What it does:** reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from the environment; if one is missing it says which and stops (exit 2, nothing sent). It sends one plain-text message, "Hello from the Forecast desk. This is a test message: if you can read it, alerts to this chat work. Nothing was bet or ordered.", with the same `TelegramNotifier.send` the watcher uses, so a pass proves the real path (not a second implementation). Exit 0 and "Sent: check Telegram." on success.
- **When it fails** it names the cause in plain words by the kind of error the sender already raises: wrong token (Unauthorized), wrong chat id or Start not pressed (ChatNotFound), bot blocked (BotBlocked), too many messages (RateLimited), Telegram not reachable (NetworkError, "check the internet and the VPN"); exit 1.
- **Secrets:** the script prints only whether each value is set, never the value; it does not configure logging, so the HTTP library's request line (which holds the token in the address) is not printed. Errors are shown by kind only, as the sender already does. (The token-in-logs bug `BUG-20261014-1225` concerns the backend's own log filter; this script never writes that line because no logging is set up. The bug stays open as the user decided.)
- **Docs:** one line in `docs/RUNBOOK.md` section 6 (Telegram set up) with the command, after the four set-up steps.

## Not done

No test message from inside the running app (the script sends from the host). No sending of alert-like messages. No Docker image change.

## Test

`backend/tests/test_telegram_script.py` loads the script and runs it with a fake sender: missing values stop it with exit 2 and the names of what is missing; success gives exit 0 and the message text above; each error kind prints its plain sentence and exit 1; the output never contains the token or the chat id (checked with distinctive fake values); the script file contains no `logging` setup and no `print` of the secret variables.

## Checks to state at close

Lateral spread: the other places that handle the token (the sender, the chat-id helper, the settings check) are unchanged; the script uses the sender, not a copy of it. Causal depth: the need is "know that delivery works"; the script proves it once, and the first real alert and the alert history on the Opportunities page ("Sent" or "Could not be sent") show it from then on.

## Result (2026-10-14)

Built as specified: `scripts/telegram_hello.py` (uses `TelegramNotifier.send`, prints only set or not set, no logging set up, named failures, exit 0, 1 or 2) and `backend/tests/test_telegram_script.py` (5 tests plus parametrized failures, 11 cases in all); RUNBOOK step 5 in section 6. Run for real on 2026-10-14 with the user's `.env` loaded in my shell: with the two values unset it stopped with exit 2 and sent nothing; with them loaded it printed "Sent: check Telegram." (exit 0). Whether the message was read in Telegram is for the user to confirm; the script only knows Telegram accepted it.

Checks done: lateral spread (the sender, the chat-id helper and the settings check are unchanged; the script reuses the sender; the output was checked for the token and chat id by the test); causal depth (it proves delivery once; the alert history on the Opportunities page shows it from now on).
