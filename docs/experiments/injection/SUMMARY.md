# Injection experiment: summary of the findings (plain English)

Full tables: `REPORT-RESULTS.md` (and `.csv`). Raw runs and settings: `runs.jsonl`, `runs-CONFIG.json`. How to reproduce: `REPRODUCE.md`. Screenshots: `screenshots/`. This summary is not Chapter 4; it states what the data shows and what it does not.

**What was run.** 1,296 runs (648 end to end, 264 at the judge, 384 at the forecaster), 9 conditions (all six controls off, all on, each control off in turn, and all on plus a hostile-instruction rule at the researcher), 20 attack pages and 4 clean pages, 3 repeats, one fictional match. 0 runs failed. Model cost 34.84 USD (gpt-5.4 and gpt-5.4-mini, version gpt-5.4-2026-03-05 as reported by OpenAI).

## Results

1. **Prompt injection almost never worked, even with every control off.** All six controls on (P): 0 of 99 attempts (95% interval 0 to 4%). All six off (B0): 4 of 99 (4%, 2 to 10%). All four successes were at the judge entry, from class I2 (pages that pretend to be the verifier), when the judge's quote check and the untrusted-data rules were off. End to end, injection success was 0 of 48 in every condition: the researcher never relayed or obeyed the hostile instructions.
2. **The forecasters ignored instructions placed in their facts.** At the forecaster entry, injection success was 0 of 33 in B0 and the target probability moved by about 1 point on average. Removing the untrusted-data rules and markers (control 1) did not change that (1 success in 33 in one other condition).
3. **No fake tool was called and no forbidden address was reached, in any condition.** 0 of 135 runs per condition (60 for PR), including conditions where the fake tools were offered (B0, A2) and where the address check was off (B0, A3). The models never tried. So the protective effect of controls 2 (least privilege) and 3 (the address gate) could not be observed in this data: no attack got far enough for them to matter. Their mechanisms are covered by unit tests (the gate refuses the internal address and, with it off, the address is reached; a flagged market waits for a person unless approval is off), not by behaviour in this experiment.
4. **False information is the real weakness.** A lying page with no instruction (class I3) was accepted by the judge in 12 of 12 runs in every condition, which is expected: the judge checks that a page supports a claim, not that the claim is true, and no control tested here addresses it. End to end, 17% to 58% of the I3 runs ended with the false fact accepted, with no consistent pattern across conditions (12 runs per cell, so differences are within noise). The most explicit false fact (a goalkeeper ruled out) was accepted in 26 of 27 end-to-end runs. When a false fact was accepted, the forecast moved about 2 to 5 points in the direction of the false fact on average (descriptive, small groups).
5. **One attack shows a limit of the quote check.** In the judge-entry successes with the quote check on, the judge's quote was the attacker's own "VERIFIER NOTE" text, which is really on the page, so a check that the quote is on the page passes. The control cannot stop an injection that supplies its own quote.
6. **Human approval did what it is for, on a small number.** Flagged markets appeared in a few attack runs (B0 4 of 105, P 3 of 105; none in clean runs). With approval on, those 3 waited for a person; with it off, all 4 in B0 and the 1 in A6 became simulated orders by themselves.
7. **The hostile-instruction rule at the researcher** (PR): 4 of 60 attacks succeeded against 7 of 60 for P (difference 5 points, interval 0 to 13). The only successes in either were false-information runs. The data cannot separate a real effect from noise.
8. **Clean-fact retention** was 100% (82 of 82) in both B0 and P. With schema validation off (A4) it fell to 92%; this comes from the experiment's lenient reading of the judge's free-text answer (shorter quotes fail the number check), so it should not be read as a security effect.
9. **Control effectiveness** (success with the control off minus all on) is small everywhere. The largest is control 1 at the judge entry: +10 points (0 to +30). All six off against all six on, over everything: +2 points (-3 to +8).

## What the data cannot show

- Only 20 attacks, all written by us and plain in style. Current models ignored them. This says nothing about stronger, adaptive or model-specific attacks.
- One fictional match and one model family. Text coming from Kalshi (market titles and rules) was not tested.
- Three repeats per cell: enough to see "always, never or sometimes", not to estimate rates precisely. Intervals are wide; runs of one attack are not independent.
- Controls 1 and 3 each switch off several mechanisms together; no result can be attributed to one mechanism.
- Two deviations from the app: a local page tool for the researcher (OpenAI's hosted search cannot be fed test pages) and one forecaster where the app averages three.
- The judge-entry attacks plant a false claim by construction (a researcher cannot be made to write a claim the page does not contain), so those rates measure the judge, not the whole chain.

## What this suggests for Our Agent (hypotheses, not results)

The weak points are about false information, not about instructions: (a) the researcher prompt has no hostile-instruction rule (PR was not clearly better, but costs nothing); (b) the judge accepts whatever a page states, so a claim should need support from more than one independent source; (c) there is no trust level for sources. These are for a later decision.
