# Spec: markdown in claims and researcher answer quality (BUG-20261012-1449, ISS-20261012-1450)

Branch: `feature/sports-games-list` (base: `master`), where the first real run was done. Both items come from the first real research run (NOTEPAD D27): Atalanta vs Venezia, 22 claims.

## BUG-20261012-1449: literal `**` in claim text

**Verified cause:** the model answers with markdown (bold markers around dates and names). `backend/app/research/claims.py` cuts out the citation link markup but leaves other markdown. 16 of the 22 stored claims contain `**`, and the result page printed them as asterisks (54 occurrences counted on the page).

**Fix:** (1) the claim cleaner removes markdown emphasis (bold, italics, backticks) and any stray `**`; (2) the researcher is told to write plain text. The cleaner is the real fix: models drift, instructions alone are not enough.

**Lateral check:** other model text shown to people: the angle names and questions from the planner (structured output; none of the four in the real run had markdown, so not changed now), and the run error messages (our own text). Nothing else prints model text.

**Tests:** bold, nested and multiple bold, italics, backticks, an unbalanced `**`, and text with a lone `*` (kept).

## ISS-20261012-1450: researcher answer quality

**Verified from the real run** (stored result of run `3833f5bb...`):
- low-value lines ("the league page showed no data", "the squad list did not name a suspension");
- the kickoff time differs between sources (16:30, 18:30; the exchange says 19:30 UTC) and the answers do not say so;
- the only odds came from a page "crawled two weeks ago";
- derived claims (days of rest) were the model's own arithmetic, cited to pages that do not state them;
- the fourth angle combined venue, rest and odds.

**Fix (instructions only; no code path changes):**
- Researchers: at most 6 lines, fewer is better than weak; plain text; state only what the page states and do not calculate or infer; give the date of the information; use odds only when the page shows a recent date (not older than 3 days), otherwise write that none were found; if a source gives a different start time from the one the exchange lists, say which source says what; no lines about what a page did not show.
- Planner: one topic per angle; the betting odds are their own angle and are never combined with other topics; ask for dates and prefer official club, league and tour pages.

**What this cannot fix:** whether a cited page really supports a claim (Milestone 3), and whether odds exist on the open web (some pages are blocked or old).

**Tests:** the instruction texts contain each rule (they are the contract with the model); the existing tests still pass. **Real check:** the same game and two more (baseball, tennis) are researched again with the real key and compared with run `3833f5bb...`; results go in NOTEPAD.
