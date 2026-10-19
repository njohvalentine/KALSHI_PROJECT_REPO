# Spec: rewrite docs/DEMO.md for the client demo

Branch `feature/sports-games-list` (base `master`). Documents only, no code.

**What is wrong now.** `docs/DEMO.md` was last updated on 2026-10-14. It does not know the Dashboard, the free bookmaker check on the Games page, the verdict (NO BET / Worth a look), the Bookmakers fold, the daily limit of 5 and the repeat warning, the stop rules and open-exposure checks on the Approval page, or the results by sport and kind. Its "close to a plain AI answer" line is out of date. Verified by reading the script, `frontend/app/(app)/*` and the button texts in the components.

**Decisions (user, 2026-10-19):** screen share from the operator's computer (the deployed server still has the old look); about 20 minutes.

**Content:** an honest opening with today's numbers (taken from the live `score-records`), the preparation (the 5-a-day limit counts 24 hours, so research the demo games the day before and do not plan live research), a fallback with the screenshots in `docs/design/screenshots-2026-10-16/`, the updated walk, the questions for him, and what not to say or show. **Not done:** no recording, no slides, no change to the README or HOW-IT-WORKS.

**Checks at close:** each page and button in the script exists in the code (checked); the numbers match `score-records` run today; no secret is named with a value.
