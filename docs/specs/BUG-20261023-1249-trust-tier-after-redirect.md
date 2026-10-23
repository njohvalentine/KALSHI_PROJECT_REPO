# Spec: the trust tier follows the page that was read, not only the address that was cited (BUG-20261023-1249)

Branch `feature/security-hardening` (base `master`). Found by the automated security review of FEAT-20261023-1130 (2026-10-23); premise verified in the code.

## What is wrong

`best_tier` / `tier_of` are computed from `ClaimCheck.source_url`, the address the researcher cited. The page fetcher follows redirects (up to a few hops, each checked for public addresses) and the judge reads the text of the page it reached; that address is saved as `SourcePage.final_url`. A cited address on a listed host that redirects to another host (an open redirect on a site that has one) would give a stranger's page the label "official". Requires an open redirect on a listed host and the cited address reaching the researcher, so it is unlikely; the fix is cheap.

## Fix

`page_tier(cited_url, final_url)` in `app/research/source_trust.py`: the lower of the tier of the cited address and the tier of the final address (`final_url` empty means no redirect: the cited address alone). `supported_claims(findings, checks, final_urls=None)` takes a `{cited url: final url}` map and uses it per supporting page. The three places that build or show a tier load the map from `source_pages`: `pipeline._supported`, `replay._claims_of` and the run detail in `runs.py`. Same-site redirects (http to https, www, a subdomain of the same listed host) keep the tier.

## Checks to state at close

Lateral: every consumer of a tier (the three above; no other code reads the tier). Causal depth: one cause (the tier was taken from the input of the fetch, not its output).

## Tests

Cited official address redirecting to an unlisted host gives "other"; official to a subdomain of the same host stays official; unlisted to official stays "other" (the lower); no final address uses the cited one; the run detail and `supported_claims` agree.
