# Spec: redesign step 6, the documents and the screenshots

Branch `feature/sports-games-list` (base `master`). Last step of the redesign. The browser tests were changed inside steps 1 to 5b, one change at a time, each run with the page it touched (login, header chip, Dashboard, Results cards, a finished run's glance and folds, the two ticket tests that open folds). What is left is the documents and the screenshots.

## What is out of date

- `docs/RUNBOOK.md` section 7 ("Looking at results") lists Games, Opportunities and Prediction only; there is no Dashboard, Results or Approval line.
- `docs/MILESTONES.md` line 27, `docs/ARCHITECTURE.md` line 115 and `docs/HOW-IT-WORKS.md` line 50 list the pages without the Dashboard.
- `docs/design/` has screenshots of 2026-10-13 and 2026-10-14 (the old look) and a sample page; none shows the app as it is now.

## Design

- Add a Dashboard line to the RUNBOOK (what it shows, where the numbers come from, what the message at the top means, the 0.005 and 30-game rules), and short Results and Approval lines; add the Dashboard to the page lists in MILESTONES, ARCHITECTURE and HOW-IT-WORKS; one sentence in MILESTONES that the redesign is done and which design file it followed.
- New folder `docs/design/screenshots-2026-10-16/` with desktop (1280 px) and phone (390 px) screenshots of the real app: sign-in, Dashboard, Games, Opportunities, Prediction list, a finished run (the NBA game, folds closed), Results and Approval. They are taken with the browser test account (`e2e@example.com`, local only) from the running stack; nothing in them is a secret (the e-mail of the test account shows in the header).
- Opportunities has no row to show right now (every researched game has started). Two ways to get one: research one upcoming game (about 0.43 US dollars of OpenAI credit; needs the user's yes), or leave Opportunities with its empty state. The user chooses; the empty state is the default.
- The final full test run: backend (556 tests), lint, build, browser tests (the three that need an upcoming researched game skip with their reason).
- The sample `mockup-redesign-2026-10-15.html` stays as the design reference.

## Not done

No change to the app. No new tests. No Opportunities screenshot with rows unless the user says yes to the one research run.

## Checks to state at close

Lateral spread: every document that lists the pages is changed together (RUNBOOK, MILESTONES, ARCHITECTURE, HOW-IT-WORKS); I search the repository for other lists of the pages and for the old "orange bar" wording. Causal depth: the need is that the documents match the app; the search covers wording as well as page names.
