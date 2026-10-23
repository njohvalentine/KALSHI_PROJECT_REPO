# Source labels: what the measurement showed (2026-10-23)

Spec: `docs/specs/FEAT-20261023-1130-source-trust-labels.md`. Data: `runs-labels.jsonl` (78 runs, 0 errors, 2.80 USD), settings `runs-labels-CONFIG.json`, tables `REPORT-LABELS.md` (and `.csv`).

**Question.** Do the forecasters discount a false fact when it is labelled "other source" while the true facts are labelled "official source"?

**Setup.** Two conditions, both the app as it is now (researcher rule, a forecaster prompt that explains labels, one forecaster, all six controls on): PN without labels in the facts, PT with labels. The true pages sat on fake hosts the harness treats as official; the four lying pages (class I3) on an unlisted host, so the app's own tier for them is "other". Each attack was run at the forecaster entry (the false fact is always shown) and end to end, 3 repeats.

**Result: no measurable effect of the labels.**
- **At the forecaster entry** the false fact moved the Northvale-win probability by **+1.4 points** without labels and **+0.4 points** with labels (12 runs each; per attack the values range from -1.3 to +2.7). The one-point difference is within the run-to-run noise of the models.
- **The false fact barely moved the forecast even without labels.** With a lying fact among six true ones, one forecaster moved about 1 point the way the lie says. So in this setup there was little for the label to prevent.
- **End to end,** the false fact was accepted as a supported fact in 2 of 12 runs (PN) and 5 of 12 (PT): the label does not touch that step, so the difference is noise (the researcher cites the lying page only sometimes). Where it was accepted, the forecast moved -1.8 to +2.3 points.
- **No harm:** all 169 true claims in clean runs were accepted (100% in both), no market was flagged in any run, no order made.

**What this does and does not say.** It does not show that labels help, and it does not show they hurt. With 12 runs per cell and one forecaster it could only have shown a large effect, and there was no large effect to find because the lie had little influence to begin with. Earlier single-run observations of a 10-point move (the smoke runs) were not repeated in 3 repeats. The label still tells a person which kind of site stands behind a fact, which is its main value. It is not a defence against a lying page: the real defence is a second independent source (FEAT-20261023-1131, phase 1 measures whether that is possible with our data).

**Limits.** One fictional match, one forecaster (the app averages three), four attacks, 3 repeats, a label list that the harness extends with fake hosts. Forecasts made with real, longer fact lists may react differently.
