# Spec: the judge's page-text marker can be imitated with lookalike characters (BUG-20261023-1251)

Branch `feature/security-hardening` (base `master`). Sibling of the item before it, found while checking it sideways.

## What is wrong

`checker_input` removes copies of `<page_text>` with `PAGE_TAG` (exact ASCII, any case and spacing). A page can contain `＜/page_text＞` (fullwidth) or put a zero-width character inside the tag; the exact pattern misses it and the model may read it as the end of the data block, followed by "instructions". The injection experiment tried the exact-ASCII spoof (attack I2-2) and it did not work, but lookalikes were not tried.

## Constraint

The judge's quotes are checked against the saved page text (`quote_is_on_page`, with its own light normalisation). Normalising the whole page text before sending it would change characters the judge quotes, so a true quote could fail the check.

## Fix (proposed)

Find the marker on a normalised copy (NFKC and format characters removed) and cut the matching span out of the **original** text (a position map from the normalised copy back to the original), so only marker lookalikes are replaced and every other character is unchanged. If that proves fragile, the fallback is to replace only the bracket-like and angle-like lookalike characters inside any span that normalises to the tag. A test checks that the quotes of normal pages with fullwidth digits or compatibility characters still match.

## Checks to state at close

Lateral: the same exact-ASCII pattern in the forecaster facts is the previous item. Causal depth: one cause. Optional measurement: add the lookalike spoofs as attacks in the injection harness (a few cents) to see whether the model is fooled at all before and after.

## Tests

Lookalike and zero-width spoofs of the page marker are removed; the page text outside them is byte for byte unchanged; true quotes from pages with compatibility characters still pass.
