# Spec: stop researching bookmaker odds (the planner's odds angle)

Branch `feature/sports-games-list` (base `master`). From the signal research of 2026-10-19 (idea 7, "cheaper research"), chosen by the user's "your call" the same day. A saving, not a signal: it removes a research step whose result is never used.

## What is there now (read in the code, measured on our 81 finished runs)

- The planner is told "Betting odds are always their own angle, with kind market_odds" (`research/prompts.py`), and lists a betting-odds angle among its examples. So every run gets four angles, one of them about odds: **76 of 81 finished runs (94 percent) have a market-odds finding.**
- That angle is researched like the others (a `gpt-5.4` call with web search), its pages are downloaded and its claims are checked, and then **nothing uses it**: `check.py` never lets claims about odds go forward ("Findings about odds or market prices never go forward"), the forecasters are told to ignore betting odds, and since 2026-10-17 the app reads the bookmakers itself from the odds feed. The run page shows it as "Market prices found (not given to the forecasters)".
- The research step is **76 percent of a run's cost** (an average of 0.331 dollars of 0.434). With four angles of equal cost, the odds angle is about 0.083 dollars per run (19 percent of the run), plus the downloading and checking of its pages (not separated in the stored costs, so not counted).

## Design

- **The planner is told not to plan an odds angle.** The rule "betting odds are always their own angle" becomes "do not plan an angle about betting odds or market prices: the system reads prices separately and the forecasters must not use them", and the odds bullet is removed from the examples.
- **A code guard, in case the planner plans one anyway:** the planning step drops any angle for which `is_market_angle` is true (kind `market_odds`, or "odds" in the name: the same test that already keeps such claims from the forecasters), counts them in the run state (`dropped_odds_angles`) and logs it. So the saving does not depend on the model obeying a prompt, and a dropped angle is visible, not silent.
- **The default number of angles goes from 4 to 3** (`MAX_RESEARCHERS`, still changeable), so the planner's three angles are all about evidence. Otherwise the freed slot would be refilled with a fourth evidence angle and nothing would be saved. Our results give no sign that more evidence helps (the accuracy report: the amount of confirmed evidence does not show a clear advantage over the plain AI), so this trades a likely small loss of evidence for a certain saving of about a quarter of the research cost. It is a default, not a limit: `MAX_RESEARCHERS=4` in `.env` brings the old amount of evidence back.
- **Not changed:** the stored old runs and their pages (an odds finding on an old run still shows), the claim checking of any odds angle that exists in old data, the forecasters' rule to ignore odds, the bookmaker feed, and the schema field `kind` (old runs carry it).
- Documented in the run guide, HOW-IT-WORKS and ARCHITECTURE (where the planner and the number of researchers are described).

## Expected effect (a prediction, to be checked on the next real run)

About 0.08 to 0.11 dollars less per run (about 19 to 25 percent of 0.434), three angles, no market-odds finding. One real run after the change confirms it (about 0.35 dollars, counted in the daily limit; only with the user's yes).

## Not done

No change to the number of forecasters, the reasoning effort, the claim checker, or the flag rules; no attempt to use the odds research for anything; no re-run of old games.

## Tests

Backend: the planner instructions no longer ask for an odds angle (the two tests that assert the old wording are changed to assert the new); a planner that returns an odds angle among others (`market_odds` kind, or a name with "odds") has it dropped, the others are researched, `dropped_odds_angles` is recorded and logged; an angle named "Form" is kept; the planner returning only odds angles fails the run clearly as an empty plan does today; the default `MAX_RESEARCHERS` is 3 and 4 still works; the cap is applied after the odds angle is dropped; the run guide and HOW-IT-WORKS numbers agree.

## Checks to state at close

Lateral spread: every place that creates or reads `market_odds` findings (the planner prompt, the graph, the checker, the run page, the replay tool) is searched and listed; old data still displays. Causal depth: the cost came from three things, the prompt asking for the angle, nothing stopping it, and the slot being refilled; all three are handled and the saving is measured on a real run.
