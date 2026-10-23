# Spec: the odds key log filter can raise from a malformed log call (BUG-20261023-1135)

Branch `feature/security-hardening` (base `master`). Side discovery while fixing BUG-20261014-1225.

## What is broken (reproduced on 2026-10-23)

`_HideKey.filter` in `app/odds.py` calls `record.getMessage()` without a guard. For a log call whose arguments do not fit its text (for example two `%s` and one argument) `getMessage()` raises `TypeError`, and a filter's exception propagates to the code that called `logger.info`. Reproduced in the new Telegram test with both filters installed: the call raised from the odds filter. The Telegram filter now guards this (BUG-20261014-1225). The odds filter is a log hiding aid, so it must never break the caller.

## Root cause

The finished message is formatted inside a filter with no fallback; the pattern was copied between the two filters.

## Fix

The same guard as the Telegram filter: `try: message = record.getMessage()` and, on any exception, fall back to `str(record.msg)`, then mask and set `record.args = None`. A test calls the filter on a malformed record and checks that nothing is raised and the key is still masked. The two filters stay separate (different patterns, different replacements); a shared base class is not worth a new module for two small classes.

## Checks to state at close

Lateral: the only other log filter in the app is the Telegram one (fixed); no other filter formats a message (searched `logging.Filter` in `app/`). Causal depth: one cause. Not live: the HTTP libraries' own log calls are well formed, so this is a robustness fix.
