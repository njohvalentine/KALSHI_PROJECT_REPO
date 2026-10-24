# Least privilege in Our Agent (control 2)

What each model role may use, where the code enforces it, and what the experiment could and could not show. Code: `backend/app/research/privileges.py`; tests: `backend/tests/test_privileges.py`.

| Role | Tools it may use | Where it is enforced |
|---|---|---|
| Planner | none | `request("planner", ...)` before the call; `check_response("planner", ...)` on the answer |
| Researcher | the hosted read-only `web_search` only | the same two checks, with `web_search` allowed |
| Judge (claim checker) | none | the same two checks |
| Forecasters (and the plain-AI baseline) | none | the same two checks |

How the two checks work.
- **Before a call:** every tool in the request must be on the role's list, or the call is refused. A developer who adds a tool to a call by mistake gets an error, not a silent new privilege.
- **On the answer:** only message and reasoning items are accepted for every role, plus the search item for the researcher. Anything else (function, MCP, shell, code, computer, file search, custom tool, or a type added to the SDK later) is refused. The refusal is logged with the role and the item type, never the content, and the call ends as an error of that run.
- There is **no setting that turns this off**.
- There is no order code in the app at all, and orders exist only as simulated orders after a person approves (control 6).

What the experiment saw. With the control switched off in the test harness (fake tools `send_report` and `place_order` offered to the researcher, judge and forecasters), **no fake tool was called in any run** (0 of 135 runs per condition). So the experiment could not measure what this control prevents, because no attack got as far as a tool call. The difference between the conditions (−2 points over all entries, interval −5 to 0) is not evidence of an effect.

What is not shown here.
- The check does not stop an attack by measurement; it makes the rule explicit and tested, so a tool cannot appear without someone noticing.
- The hosted web search runs inside OpenAI. We cannot gate or log what it does inside; we only see its answer.
- The experiment's own model calls are separate code and do not pass through this check.
- The tests use fabricated answers; they show the check refuses them, not how a real model would behave.
