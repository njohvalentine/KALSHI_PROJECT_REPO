# Spec: the block markers are found on a skeleton, so invisible characters cannot hide them (BUG-20261023-1312)

Branch `feature/security-hardening` (base `master`). From the automated security review of BUG-20261023-1251 and BUG-20261023-1250 (third round, 2026-10-23). Premise checked in `prompts.py`.

## What is wrong

`remove_page_tags` (judge) and `_one_line` (facts block) match the markers `<page_text>` and `<checked_facts>` after Unicode compatibility normalisation and removal of **format characters only** (category Cf). Other default-ignorable characters can still be put inside a marker: variation selectors, U+034F (combining grapheme joiner), other combining marks, and the Hangul filler characters (U+115F, U+1160, U+3164, U+FFA0, which are letters by category). `<page_te\uFE0Fxt>` is not matched by the pattern, and a model may still read it as the marker.

## Root cause

The matching removes known kinds of invisible character instead of looking at the visible skeleton of the text.

## Fix

One helper, `_cut_markers(text, pattern)`, for both markers. It builds a skeleton of the text: NFKC per character, then keep only letters, digits and `<` `>` `/` `_`, and drop everything else (spaces, punctuation, all combining marks, variation selectors, format characters), plus the four Hangul fillers which are letters. It runs the marker pattern on the skeleton and maps each match back to the original positions, cutting that span out of the **original** text and putting "[tag removed]" there. Every other character, and so every quote check, stays exactly as it was (the same property as today's fix). `remove_page_tags` and the facts path both use it; the facts path keeps its own NFKC step for the visible text.

## Residual limits stated now (not fixed here)

Homoglyphs from other alphabets (a Cyrillic "а" for a Latin "a") are not mapped: that needs a confusables table that is not in the standard library. A marker with no closing `>` still swallows the rest of the text (the pattern's long-standing behaviour, it fails safe). The researcher's input (Kalshi title and rules) has no markers around it. **Context from the injection experiment:** with every control off, including no markers and no sanitiser at all, the forecasters followed an injected instruction 0 of 33 times and the judge was fooled only by pages that pretend to be the verifier (4 of 99 attempts), so this hardening is defence in depth against attacks the models did not follow even unprotected.

## Checks to state at close

Lateral: both markers now use the same helper; the labels are protected by the bracket rule (separate). Causal depth: one cause.

## Tests

Spoofs of each marker using a variation selector, U+034F, a combining accent, each Hangul filler, a zero-width character and the fullwidth form are removed; the text around them is byte for byte unchanged; true quotes from pages with compatibility characters still match; all existing marker tests pass.
