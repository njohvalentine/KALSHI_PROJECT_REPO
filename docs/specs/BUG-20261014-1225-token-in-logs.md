# Spec: the Telegram token reaches the log (BUG-20261014-1225)

Branch `feature/sports-games-list` (base `master`). For approval; the fix is not written yet.

## What is broken (reproduced)

`app/telegram.py` `_HideToken` is a log filter on the `httpx2`, `httpx` and `httpcore` loggers. It rewrites `record.msg` and replaces only the arguments that are `str`. The HTTP library logs a request as `'HTTP Request: %s %s "%s %d %s"'` with the URL as a URL **object**, so the argument is not a string, is left alone, and is printed with the token in it. Reproduced on 2026-10-14 with a real `httpx2` request through a mock transport: the output contained `https://api.telegram.org/bot<TOKEN>/sendMessage`. The existing test `test_the_token_is_hidden_from_the_http_libraries_log_lines` passes only because it logs strings by hand.

The token is a secret that gives control of the bot. Telegram is not switched on yet (no token in `.env`), so nothing has leaked; it would on the first message.

## Root cause

The filter masks the pieces of a log call instead of the finished message, and the pieces are not always strings.

## Fix

Mask the finished message, as the new odds filter (`app/odds.py`, built the same day) already does: `record.msg = TOKEN_IN_TEXT.sub("bot<hidden>", record.getMessage())` and `record.args = None`. The regex is unchanged. The test is replaced by one that sends a real request through a mock transport and checks the captured log (the odds test does the same), and keeps a second case for a message with the token in the text itself.

## Checks to state at close

Lateral spread: the other places that put a secret in a URL or log a URL: the odds key (same defect, fixed in its own filter and tested with a real request); the Kalshi calls carry no secret in the URL (the signing key is only used to sign headers in the key-check script); OpenAI and LangSmith keys travel in headers, not in addresses; the page fetcher logs the cited page URLs, which are public. Causal depth: one cause (masking the pieces), two affected filters.
