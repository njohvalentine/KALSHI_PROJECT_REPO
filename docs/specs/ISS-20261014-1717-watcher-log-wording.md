# Spec: out-of-date wording about the chat channel (watcher log and comments)

Branch `feature/sports-games-list` (base `master`). For approval; not changed yet. Asked for by the user on 2026-10-14 ("fix the watcher log wording").

## What is wrong (verified)

- `backend/app/config.py` line 349 logs, when the watcher is on: "The watcher is ON (every N min). Alerts are recorded in the app; no chat channel is configured." This is always printed, also with `ALERTS_ENABLED=true`, when the app does send alerts to Telegram (seen on 2026-10-14 right after Telegram was switched on, the line right above it says "Alerts are sent to a Telegram chat").
- Two comments are also old: `backend/app/monitor.py` module docstring ("A chat channel can be added behind `deliver`; none exists yet") and the docstring of `deliver` ("None is configured yet, so an alert is only recorded in the app").
- Checked and correct, so not changed: `Monitor.deliver` really sends when a notifier exists; the Opportunities page text depends on the monitor's `channel` field and already says "also sent to chat"/"Telegram"; `docs/RUNBOOK.md` section 6 describes Telegram correctly.

## Cause

The line was written before the Telegram sender existed (the item that built the sender, FEAT-20261013-1324, did not touch it).

## Fix

The log line says where alerts go by the setting that decides it: "Alerts are sent to Telegram and recorded in the app." when `ALERTS_ENABLED=true`, otherwise "Alerts are only recorded in the app." The two comments are rewritten to match what the code does. No behaviour changes.

## Test

A test of `load_settings` with the watcher on, once with and once without alerts, capturing the log: the watcher line names Telegram in the first case and never says "no chat channel" in either. Existing tests still pass.

## Checks to state at close

Lateral spread: every sentence in code, docs and pages that says no chat channel exists or is configured (config line, two monitor comments; the page and the runbook were read and are right). Causal depth: one cause, the old wording; the same line's other facts (interval, automatic research) are unchanged.
