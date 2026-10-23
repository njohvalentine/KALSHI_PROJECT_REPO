# Spec: independent corroboration of facts, measurement first (FEAT-20261023-1131)

Branch `feature/security-hardening` (base `master`). From the injection experiment (lying pages are accepted). Decision (user, 2026-10-23): when only one source supports a fact, keep it and label it.

## What the data says (app database, 2026-10-23)

Of **755 supported claims, all 755 are backed by exactly one website** (none by two or more). Cause (verified in `prompts.py` and `claims.py`): the researcher writes one fact per line and each line cites one page, and the judge checks each claim only against the page(s) it cites. So "the fact is supported by two independent pages" cannot happen with the current design, and a label based on it would mark every fact "single source", carrying no information. A run has about 12.9 saved pages and 9.3 supported claims, so other pages are available to check against.

## Design (two phases; phase 2 only after the numbers)

**Phase 1, measurement, no change to the app.** A read-only command `corroboration-test` over saved runs: for each supported claim, the judge is asked about the pages of the same run that are from other hosts than the page(s) that already support it (same judge, same quote and number checks). It reports: the share of supported claims that get a second independent host, by sport; the cost per run (judge calls on the saved pages, about 0.02 to 0.04 USD per run); and, by hand on 20 claims, whether the second page really states the same fact. It runs on a sample of 30 saved runs first (about 1 USD). "Independent" means a different registered domain (a short list of two-part suffixes such as co.uk is built in); two sites that print the same wire story are not independent, and this is not detectable here (stated as a limit).
**Phase 2, only if the user approves after reading phase 1.** A corroboration pass in the pipeline after the normal check, a count of independent hosts per claim added to the label of the trust spec (`FEAT-20261023-1130`: depends on it), the result page, and the forecaster input; the flag rule stays unchanged. Its effect is measured with the injection harness (condition "PC", the I3 attacks) like the trust label.

## Rule fixed before phase 1

Phase 2 is worth proposing only if at least 25 percent of supported claims get a second independent host and the hand check finds the second page states the same fact in at least 17 of 20 cases. Below that, the result is reported and phase 2 is not proposed.

## Limits stated now

Syndicated copies look independent; the judge may over-accept a second page that states a similar fact; one page per claim is also an effect of the researcher prompt, which could instead be asked to find a second source (a different, costlier change, named here and not chosen).

## Tests

Phase 1: the registered-domain function (co.uk, www., subdomains); the selection of pages from other hosts only; the report arithmetic on a known case; the command writes nothing to the database. The full suite passes.
