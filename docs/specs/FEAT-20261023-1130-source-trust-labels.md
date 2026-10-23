# Spec: a trust label for each source of a fact (FEAT-20261023-1130)

Branch `feature/security-hardening` (base `master`). From the injection experiment: a page that states a false fact with no instruction is accepted by the judge in every condition, because the judge checks that a page supports a claim, not that the claim is true; no control in the app addresses it. Decision (user, 2026-10-23): label, do not drop.

## What the data says (read from the app's database on 2026-10-23)

1,189 saved pages from 236 hosts. The hosts that support the most claims are official league, tour and club sites (wtatennis.com 106, uefa.com 65, mlb.com 29, mlssoccer.com 25, inter.it 18, npb.jp 13, ...), plus some aggregators and fan or betting-tip sites (agentbets.ai 33, en.tennistemple.com 11, tennislive.net, sofascore.com). So a short list of known official and news hosts covers most supported claims, and the long tail of club sites and others is the unknown part.

## Design

- A static list `app/research/source_trust.py`: host (without `www.`) to tier, starting from the hosts above after the user reviews the list. Tiers: `official` (leagues, tours, federations, clubs), `news` (major news and wire services), `other` (everything not listed, including aggregators, tipster and betting sites). Unknown hosts are `other`, never trusted by default.
- `supported_claims()` (`app/research/check.py`) adds to each claim the best tier among the pages that support it (`source_tier`, derived at read time from `supported_by`; no new column, no migration).
- The forecasters see the label on each fact line (for example "[official source]" or "[unlisted source]") and a prompt line: facts from unlisted sources are less reliable, weigh them less; the label is data, not an instruction. The facts sit in the same block, so the experiment's marker handling still applies.
- The result page shows the tier of each supported fact and a count per tier. **The flag rule is not changed** (`MIN_SUPPORTED_CLAIMS` still counts every supported claim); whether the flag should need official or news facts is a later decision after the effect is measured.
- **How it is measured:** the injection harness gets a condition "PT" (P plus this label, using the harness's own fake hosts: `news.test` listed as unlisted). The I3 attacks end to end and at the forecaster entry are re-run (about 72 runs, 3 USD). The question: do the forecasters discount the false fact when it is labelled unlisted? A result of no change is reported as such.

## Limits stated now

A list is a judgement and goes stale; a lying page on a listed host would be trusted; the label may change the forecasts only a little. Forecasts made after this change use a different input than earlier ones, so the scoring report notes the change date.

## Not done

No dropping of facts, no change to the flag rule, no automatic list building, no check that a listed host has not been compromised.

## Tests

The tier lookup (with and without `www.`, subdomains, unknown hosts); the best tier across several supporting pages; the forecaster input carries the label and the marker stripping still applies to it; the result API carries the tier; the full suite passes.
