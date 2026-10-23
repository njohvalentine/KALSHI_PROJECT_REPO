# Spec: a ranked list of the most probable outcomes, with the Kalshi price and the gap beside each (FEAT-20261022-0955)

Branch `feature/security-hardening` (base `master`; the item is independent of the security work, and the branch is the one checked out). From the client's messages of 2026-10-22: "identify and rank the most probable winning opportunities across available markets", each with "estimated winning probability, confidence level, supporting evidence, risks and comparison with Kalshi prices"; "a simple dashboard showing the strongest opportunities"; his answer 1: **show both side by side** (probability and gap). Soccer first (his answer 3).

## What is there now (read in `app/opportunities.py`, `app/research/predict.py`, `compare.py`)

- The Opportunities page has **one row per game**: the single best market by gap (`build_row`), flagged or not, with the verdict. It is ranked by gap, not by probability, and it hides the other markets of the game.
- Everything the new list needs already exists per market: `prediction.outcomes[]` (probability, the three forecasters' range as `spread`, the outcome label, the kind), the fresh comparison from `evaluate_game` (the price of each side, the gap after fees, the flag and its reasons, the bookmakers' view for winner markets), `supported_claims`, `evidence`, `source_tiers` (new), the forecast age, and whether the sport has scored results.
- Nothing ranks outcomes by probability, and nothing says how confident a forecast is.

## Design

**One row per market, on its more probable side.** For each market of each researched game that has not started: the side is "yes" when our probability is at least 50% and "no" otherwise; the row shows our probability for that side, the range of the three forecasts, Kalshi's ask for that side, the gap after fees for that side (our probability minus the ask minus the fee, the same arithmetic as the comparison), the bookmakers' probability for winner markets, the flag from the app's own rule, the evidence (supported claims and how many come from official, news and other sources), and the risks in words.

**Two orders, both visible: "Most probable" (the default, as the client wrote) and "Biggest gap".** A row shows both numbers, so the near-certain favourite priced at the same level is visible as a safe pick with no gap, which is the point the reply to the client made. A filter hides outcomes priced at 95 cents or more (nothing to gain there), on by default and switchable. Filters for sport (all sports by default; soccer is what the client uses first) and for kind of market.

**Confidence level: a rule, shown with its reasons, not a probability of being right.**
- *Low* if the forecast is stale (older than `OPPORTUNITY_MAX_AGE_HOURS`), or fewer than `MIN_SUPPORTED_CLAIMS` facts are supported, or the three forecasts disagree by more than 10 points.
- *High* if none of that holds and the forecasts agree within 5 points and at least 8 facts are supported and at least half of them come from official or news sources.
- *Medium* otherwise.
The label always comes with its reasons ("forecasts agree within 3 points; 11 supported facts, 8 from official sources"). The page says what it is: how consistent our three forecasts and the evidence are. **The page also says, with the current numbers, that on the finished games Kalshi's price was more accurate than our forecasts.**

**A check of the label before it ships (descriptive, from our own records).** The same rule, applied to the scored records (spread, supported claims, the sport; the age cannot be known), and the Brier score of our probability within each label, next to Kalshi's price on the same outcomes. If "high" is not better than "low", the page says so in its help text (the number goes in the notes). The label is not changed to look better.

**Risks, in words:** the existing reasons of the comparison; forecast stale; thin evidence; all facts from "other" sources; our probability differs from Kalshi's price by 15 points or more ("a model error is more likely than an opportunity", the app's own rule); the bookmakers disagree with us; the sport has no scored results; the forecasters disagree.

**Where:** a new backend module `app/ranking.py` (a read-only `GET /api/ranking` with the same 60 second cache and login as Opportunities, reusing `collect()`), a new page `Ranking` in the menu, and a short card of the top five on the Dashboard (a second commit). No model call, no research, no database change.

## Not done

No new market kinds (first half, corners: FEAT-20261022-0957); no automatic updates when a forecast or price changes (FEAT-20261022-0958); no change to the flag rule or the verdict; no "Add to ticket" button on the ranking rows (the ticket flow stays on Opportunities and the run pages; can be added if wanted); no cross-game combination logic.

## Checks to state at close

Lateral: the same side, gap and fee arithmetic as `compare.py` (a test compares the ranking's gap with the comparison's `net_edge` on the same market); the confidence rule used in one place only. Causal depth: the client's request has two needs, to see the likely outcomes and to see whether they are good value; both numbers are on every row, and the honest accuracy statement is on the page.

## Tests

The side choice and the probability of that side; the gap equals the comparison's edge for the same side; both sort orders; the 95-cent filter; the confidence rule on a table of cases (stale, thin, wide range, high, medium) with its reasons; the risks; games that have started are left out; the endpoint needs a login; the validation function on a small known set of records. The full backend suite, the frontend lint and build, and a screenshot of the page in the notes.

## Changes after the first version, approved by the user (2026-10-23)

The first version ran on real data (three researched Champions-and-league games, screenshot `docs/design/screenshots-2026-10-23/ranking-first-version.png`) and showed two design faults, both reported before being changed:
1. **The "more probable side" rule gave every outcome of a three-way match as "no"** ("Monza wins: no 78%"), and the real most probable result ("Torino wins 47%") never appeared. **Now a match result (the winner markets) always shows the outcome itself (the "yes" side);** any other market keeps the more probable side.
2. **The 95-cent default hid nothing** (0 of 36 rows) and the top of the list was near-certain markets with no gap ("Over 5.5 goals: no, 94%"). **The default is now 90 cents** (7 of 36 rows were at 90 or more); the filter can still be switched off.
3. **The Dashboard card shows the five most probable match results only** (winner markets), not every market.
4. **The table is tighter:** evidence moved into the confidence cell and the risks into a fold, so the table fits a normal screen.
Also measured: the first ranking load takes about 7 seconds (the Kalshi reads, as on Opportunities, about 4.7); a second load within a minute takes 0.01 seconds; the database work is 0.2 seconds in all, so it was not the cause.

