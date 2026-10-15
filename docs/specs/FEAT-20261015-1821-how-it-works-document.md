# Spec: a plain-English document of how the system works

Branch `feature/sports-games-list` (base `master`). Asked for by the user on 2026-10-15; the outline was approved as "yes". Documentation only.

## Why

The explanation of the system is spread over `ARCHITECTURE.md` (technical), the run guide, the notepad of decisions, and many specs. A manager or the client has no single readable description of what the system does, which parts are AI agents, and which terms mean what.

## Design

One file, `docs/HOW-IT-WORKS.md`, in complete sentences, no shorthand. Sections: what it is for; the big picture in order; the parts; the agents; the strategies; how it is measured; results so far (short, linking `docs/ACCURACY-REPORT-2026-10-15.md`); a glossary; limits and open items. A technical last section for developers names the files.

Every statement is checked against the code (research graph, prompts, forecasting, the flag rule and fees, scoring, the watcher, tickets, discovery) before it is written. Where the code and the existing documents disagree, the code wins and the difference is reported to the user.

## Not done

No code change. No copying of the run guide; the document links to it.

## Checks to state at close

Lateral spread: terms used in the README, the run guide and the accuracy report are checked against the glossary so they are not defined two ways. Causal depth: the need is that a non-technical reader can understand what the system does and does not do; the glossary and the agent descriptions cover the terms that appear in the app itself.
