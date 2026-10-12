# Spec: wrong game start times (BUG-20261012-1500)

Branch: `feature/sports-games-list` (base: `master`). Found when the researchers in the comparison runs (NOTEPAD D28) reported that sources gave a different start time from the one we told them.

## Verified cause (live Kalshi data, 2026-10-12)

- We use the markets' `occurrence_datetime` as the game start (`backend/app/games.py` `build_game`, `backend/app/research/schemas.py` `GameInfo.from_kalshi_event`). On every game checked it is **identical to `expected_expiration_time`**: the expected settlement time, not kickoff.
- Real kickoff comes from Kalshi's milestones (`GET /milestones`, `start_date`; `primary_event_tickers` lists the game's events). Compared with the league's and MLB's own pages, which the researchers found:

| Game | Milestone start | Our `occurrence_datetime` | Sources said |
|---|---|---|---|
| Atalanta vs Venezia | 16:30 UTC | 19:30 UTC (3 h late) | 16:30 UTC (Lega Serie A) |
| Dodgers vs Brewers, game 2 | 21:00 UTC | 03:00 UTC next day (6 h late) | 5 p.m. ET = 21:00 UTC (MLB) |
| Hurkacz vs Davidovich Fokina | 11:10 UTC | 07:00 UTC (4 h early) | not checked |

- Effects: the Games page showed wrong start times; the "started" test and hiding used the wrong time (a game in play looked upcoming); the agents were told a wrong "Starts:" line and wrote spurious discrepancy lines.
- `GET /milestones` requires `limit`; a bulk call (`category=Sports`, `minimum_start_date`, `limit=500`) returned 1,475 milestones in 3 pages and 21.5 s on the VPN, and contained all four sample games.

## Fix

1. **Games list:** one bulk milestones fetch (category Sports, starting 48 hours back so games that Kalshi still has open after they started are covered), all pages (at most 10), mapped by every ticker in `primary_event_tickers` and `related_event_tickers` (earliest start wins), cached for 10 minutes separately from the games (kickoff times rarely change; the games are cached for 1 minute). It runs in parallel with the series fetches. A game's `starts_at` is its milestone start; `closes_at` stays Kalshi's close time.
2. **No silent fallback:** a game without a milestone has `starts_at: null` (shown as "–"); if the milestone fetch fails, all start times are null and the response carries a note ("Start times are unavailable right now") that the page shows; a failed fetch is retried after 10 s, not 10 minutes. Occurrence time is never used as a start time again.
3. **Run start:** one milestones call by `related_event_ticker` (`limit=5`) after the event is fetched; its start goes into the game description. On failure the run still starts with no start time (a log warning) rather than telling the agents a wrong one. The agents are shown the line "Scheduled start (exchange): ..." only when it is known.

## Lateral check

`occurrence_datetime` was used in two places only (games list, game description); both are fixed. `close_time` is used as "closes_at" and is correct for what it is. The Games page's "started" hiding now follows kickoff, so games in play are hidden by default (they still show with "Show started games").

## Not changed / limits

- The 10-minute milestone cache is in memory; a restart refetches (about 21 s on the VPN, probably far less from the client's network; the games list shows its loading state meanwhile).
- If a league's games have no milestone (not seen in the sample), they show "–" for the start and sort last.

## Tests

Start from the milestone and not from the occurrence time (they differ in the fixtures); bulk fetch pages, lookback and category parameters; mapping from primary and related tickers, earliest wins; separate caches (one milestones call across two game refreshes); failure gives null starts plus a note and a 10 s retry; run start uses the milestone, falls back to no start on failure, and the prompt omits the start line when unknown.
