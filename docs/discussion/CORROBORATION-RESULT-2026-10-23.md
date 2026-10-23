# Corroboration, phase 1: what the measurement showed (2026-10-23)

Spec: `docs/specs/FEAT-20261023-1131-independent-corroboration.md`. Data: `CORROBORATION-PHASE1-2026-10-23.md` (the report, with the hand-check sample) and `.jsonl` (every claim with its websites). Read-only, 30 saved runs picked by seed 20261023, 1.22 USD, 0 failed judge calls.

**Question.** Of the facts a run found, how many could be supported by a second, independent website among the pages that run had already read?

**Result: 11 of 243 supported claims (5%) got a second independent website.** Soccer 7 of 145 (5%), tennis 4 of 70 (6%), baseball 0 of 28. 232 claims had one website, 10 had two, 1 had three. Nine of the 30 runs had at least one corroborated claim.

**The rule fixed before the run:** phase 2 only if at least 25 percent of the claims get a second website and the hand check finds the second page states the same fact in at least 17 of 20 cases. **The first condition is not met (5% against 25%), so phase 2 is not proposed.** I still read the sample (there are only 11, fewer than the 20 the rule assumed): of the ten I read in full, all ten second pages state the same underlying fact (the sports facts were fixtures, standings, scores and tournament dates). In one (a kickoff time) the quoted passage shows the match but not the time, which the judge's reason says it found nearby.

**Why so few, from the data.**
- **The facts mostly have one source by nature.** The facts that matter most to a forecast (line-ups, injuries, team news, a club's own preview) are published by the club or league itself; other sites copy them later or not at all. About half of the claims (135 of 243, 56%) are written as statements about a page ("the club's official preview lists..."), which describe their source and cannot be confirmed by another page as worded.
- **The researcher does not look for a second source.** It writes one fact per line and cites one page; the pages in a run are not chosen to overlap.
- **Our own earlier finding stands:** all 755 supported claims in the database had exactly one website, and only a second look at the pages already read finds a few more.

**What this means for the lying-page weakness.** Requiring or labelling "two independent sources" would mark almost every fact single-source, so it cannot separate true facts from false ones in our data. The source label (official, news, other) is what we have, and it showed no measurable effect on the forecasts. The honest position: a lying page that the judge accepts reaches the forecasters, and no cheap check we built or measured stops it. The options that remain are different projects: ask the researcher for a second source on the claims that matter (more searches, more cost), compare a fact with the match's own results afterwards, or accept the risk as small (in the experiment a false fact moved a forecast by about 1 point).

**Limits.** 30 runs of 100+ saved; one judge model and the app's own quote and number checks (strict, so it may miss a second page that states the fact in other words); "independent" means a different registered domain, so two sites printing the same wire story would count as two; the pages are only those the researcher happened to read.
