# Spec: soccer first-half markets (FEAT-20261022-0957)

Branch `feature/security-hardening` (base `master`), as for the items before it. Scope approved by the user on 2026-10-23: first-half only; corners are split out as a wish; test on the Premier League now, the Champions League by the same ticker rule.

## What is wanted

The client asked for soccer markets "one at a time", Champions League first. Our Agent today forecasts the winner market of a game plus total goals, both teams to score and margin. The first-half versions of these should be forecast and tracked the same way.

## What I verified (read live on Kalshi, 2026-10-23, VPN on)

- Premier League, Aston Villa vs Man City (`KXEPLGAME-26OCT24AVLMCI`): the same suffix exists in `KXEPL1H` (3 markets: home wins 1st half, away wins 1st half, Tie 1st half; they are exclusive), `KXEPL1HTOTAL` (over 0.5, 1.5, 2.5 first-half goals), `KXEPL1HBTTS` (1 market), `KXEPL1HSPREAD` (a team wins the first half by more than 1.5 goals). Also open now: 1st-half correct score (15 markets), second-half winner, total and team corners (not in this item).
- Champions League: the series exist (`KXUCL1H`, `KXUCL1HTOTAL`, `KXUCL1HBTTS`, `KXUCL1HSPREAD`), but **no event is open**, also not for the games of 3 Nov. So the live check for the Champions League has to wait until Kalshi lists them; the ticker rule is the same, which is the only thing that can be checked today. The note of 2026-10-15 that "Kalshi lists them" was right about the series, not about every game at every time.
- The fee type of the first-half series is `quadratic` (the winner series is `quadratic_with_maker_fees`); the records read the fee per market, so nothing to change (to be confirmed by a test).
- Code read: `research/markets.py` (`COMPANIONS`, `companion_ticker`, `group_from_event`, `attach_companions`), `schemas.py` (`MarketGroup`, `GameInfo.sums_to_one`, `kind_of`), `forecast.py` (`enforce_consistency`, `validate_full`), `prompts.py` (`GROUP_HEADINGS`, `GROUP_RULE`), `ranking.py` (match results always show the "yes" side, line 80), `records.py` (bookmaker prices only for winner markets), `models.py` (`market_kind` is `String(10)`), frontend `labels.ts`, `types.ts` (`MarketKind`).
- Lineup updates and the replay tool read the game's groups from the saved data, so they pick up the new kinds without a change.

## Design

1. **Find the markets.** In `COMPANIONS["Soccer"]` add four kinds: `h1_winner` (ticker part `1H`), `h1_total` (`1HTOTAL`), `h1_btts` (`1HBTTS`), `h1_spread` (`1HSPREAD`). A market that is not offered for a game is noted ("not offered for this game"), never guessed, as now. Names are at most 10 characters, so **no migration**.
2. **Names and prompt text.** `KIND_NAMES`, `GROUP_HEADINGS` and the forecaster text get plain headings ("First half: winner", "First half: total goals", ...). The forecaster is told to start from its full-game numbers; no base-rate number is given (I have not verified one).
3. **Consistency rules** in `enforce_consistency` (small gaps are lowered and reported, large ones make the answer invalid, as now):
   - `h1_winner`: the three outcomes add up to 100% and are scaled, like the match result. This needs the sum rule to apply to this group too (today `sums_to_one` is only for the winner group).
   - `h1_total`: a higher line is never more likely than a lower one.
   - `h1_total` at a line is never above `total` at the same line.
   - `h1_btts` is never above `btts`, and never above first-half over 1.5.
   - `h1_spread`: a team's first-half win by more than 1.5 is never above that team's first-half win.
   - Not added: "winning the first half is less likely than winning the game". That is false.
4. **Screens and ranking.** `h1_winner` is a three-way result like the match result, so the ranking shows its "yes" side. Labels and `MarketKind` get the four kinds. The Dashboard "by kind" tables and `score-records` already split by kind, so each kind gets its own line; nothing else changes. Bookmaker prices stay winner-only.
5. **Research.** Unchanged. First-half markets use the same facts as the full game (form, lineups, injuries); no new researcher angle.

## Costs and limits stated up front

- The forecaster sees about 8 more questions per soccer game (3 + 3 + 1 + 2 = 9, minus markets Kalshi does not list); the cost per game rises slightly. I will report the measured cost on the first live run.
- The first-half winner and the full-game winner are not independent, and the markets of one game move together, so the number of games matters, not the number of outcomes. Each new kind needs about 50 games before its Brier line means anything. Nothing measured so far suggests an edge in any market; this adds markets to look at, not proof.
- Not done: corners (wish logged), first-half correct score, second-half markets, other sports, a Champions League live check (waits for open markets).

## Tests (first, backend, mocked Kalshi)

The companion ticker for each new part; `group_from_event` for each shape (the three-way first-half winner with Tie, the over lines, the single both-teams-to-score market, the spread); a game where one of them is not offered gets a note; each new consistency rule (lowered by a small gap, invalid by a large gap); the sum-to-one scaling of the first-half winner; the ranking shows the "yes" side for `h1_winner`; `kind` fits the `market_kind` column. Then one real check on a Premier League game (a paid research run of about 0.5 USD, with the user's go-ahead before it starts).

## Checks to state at close

Lateral spread: every other place that treats `"winner"` as the exclusive group (ranking, records bookmaker rule, `sums_to_one`) was read and either changed or ruled out here. Causal depth: the request has one reason (more soccer markets for the client's chosen league); the Champions League listing gap is stated, not worked around.
