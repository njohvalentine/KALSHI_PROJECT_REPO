# Spec: a fact cannot imitate a label or a facts-block marker (BUG-20261023-1250)

Branch `feature/security-hardening` (base `master`). Found by the automated security review of FEAT-20261023-1130 (2026-10-23).

## What is wrong (verified)

`LABEL_IN_TEXT` in `app/research/prompts.py` matches only the ASCII text `[official source]`. Unicode normalisation turns the fullwidth `［official source］` into `[official source]`, so a model can read it as ours; a zero-width character inside the words defeats the pattern. The same exact-ASCII matching guards the block marker `FACTS_TAG` (`<checked_facts>`), so `＜/checked_facts＞` is a lookalike too. The angle name goes into the prompt with only whitespace cleaning. Effect: a fact could claim a higher tier than it has (labels only weigh a fact, they never drop one) or imitate the end of the facts block.

## Root cause

The sanitiser removes known spellings instead of making the delimiter impossible to forge.

## Fix

One function `_clean_fact_text` for fact text and the angle name: Unicode NFKC, remove format characters (category Cf: zero-width and similar), then replace every square-bracket-like character (ASCII, fullwidth and the CJK brackets `〔〕【】「」『』⟦⟧`) with a round bracket, and run the existing `FACTS_TAG` removal on the cleaned text. Our labels are then the only square-bracketed text in the facts block (a delimiter the facts cannot contain), which is the option the review suggests. `LABEL_IN_TEXT` is no longer needed and goes. Facts with square brackets show round ones (harmless).

## Not done here

The judge's page-text marker (`PAGE_TAG` in `checker_input`) has the same exact-ASCII weakness, but the judge's quotes must match the saved page text, so normalising the page text could break a true quote; it is its own item (see the next one).

## Checks to state at close

Lateral: every place text from the web or Kalshi goes into a prompt: facts and angle (here), the judge's page text (next item), the researcher input (game title, sub title, rules from Kalshi: no markers around it, listed as a limit). Causal depth: one cause.

## Tests

Fullwidth, zero-width, mixed-case and parenthesised spoofs of a label and of both facts-block tags are neutralised; a normal fact with brackets keeps its meaning; the real labels still appear once per fact; the existing prompt tests pass.
