# Spec: the Ranking market filter shows internal names (BUG-20261104-1020)

Branch: `master` (checked out; the project merged on 4 Nov and nothing else is open). One small commit.

## What is broken

On the Ranking page the "Market" filter buttons read `btts`, `h1_btts`, `h1_spread`, `h1_total`, `h1_winner`, `spread`, `total`, `winner` instead of plain English (seen on 4 Nov on the fresh copy; screenshot `docs/user-guide/g08-ranking.png`).

## Verified root cause

`frontend/app/(app)/ranking/page.tsx` line 165 renders `{k}`, the kind key the backend sends in `kinds`. The plain labels already exist in `frontend/lib/labels.ts` (`KIND_HEADING`: "Who wins", "Total goals, runs or points", "Both teams to score", "Margin of victory", and the four "First half: ..." labels) and the other pages use them (Dashboard tables, run page, forecasters). This page was the one that did not.

## Fix

Show `KIND_HEADING[k] ?? k` on the button; the link still carries the key (`?kind=h1_winner`), so the filter and old links work as before. No backend change.

## Checks

Lateral spread: I searched every place that renders a kind (`.kind`, `kind}`, `by_kind`): the Dashboard group table, the run page and the forecasters already use `KIND_HEADING`; the alert kinds use `ALERT_KIND`; this button was the only raw one. Causal depth: one cause (a missing lookup); the "or k" fallback shows the key for a kind that has no label yet, which is visible rather than hidden.

## Test

Browser test (Playwright, `frontend/e2e`): on the Ranking page no filter button looks like an internal name (`h1_total`, `btts`, `winner` ...). It needs a researched game that has not started; with none, the test says so and skips. Plus lint and type check, and a screenshot of the real page.
