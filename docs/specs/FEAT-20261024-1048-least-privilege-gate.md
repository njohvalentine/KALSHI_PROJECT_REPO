# Spec: least privilege as an enforced control (FEAT-20261024-1048)

Branch `feature/security-hardening` (base `master`). Approved scope (user, 24 Oct): code check plus tests, no new experiment.

## What is wanted, and the reasons behind it

The client's dissertation lists six controls. His new diagram keeps four and drops least privilege and tool gating, because the experiment could not observe them. He asked (24 Oct, 00:15) whether the control can be re-established. Two reasons stack up:
1. He wants least privilege visible as a control of the project, not only a property that happens to hold.
2. The experiment found no effect (0 of 135 runs per condition called a fake tool), so there is nothing to show unless the control is explicit and testable on its own.

I say plainly: this does **not** produce an attack measurement. It makes the control real and checkable. The data from the experiment stays as it is: the effect could not be separated.

## What is there now (read in the code, 24 Oct, openai 3.29.0)

Four places call the model: planner and researcher (`research/model.py`), judge (`research/check.py`), forecasters and the plain-AI baseline (`research/forecast.py`). Only the researcher passes `tools` (the hosted read-only `web_search`, `tool_choice="required"`). The others pass none. Nothing in the code states this as a rule and nothing refuses a tool call if one ever appeared (a future change that adds a tool would go unnoticed). The injection harness (`backend/experiments/injection/stages.py`) makes its own model calls with its own fake tools and does not use these classes.

## Design

New module `app/research/privileges.py`:
- `ALLOWED_TOOLS = {"planner": (), "researcher": ("web_search",), "judge": (), "forecaster": ()}` (the baseline is a forecaster).
- `request_tools(role, tools)`: called before the model call; raises `PrivilegeViolation` if a requested tool type is not allowed for the role. The researcher's request is built from this list.
- `check_response(role, response)`: called on each answer. An allow-list of answer item types, not a deny-list: `message` and `reasoning` for every role, plus `web_search_call` for the researcher. Any other item (function, MCP, shell, code, computer, file search, custom tool, ...) raises `PrivilegeViolation`, which is logged with the role and the item type only (never the content) and ends that call as an error of the run, like other model errors. An allow-list means a new item type added by the SDK is refused until someone decides.
- `PrivilegeViolation` is a `ResearchModelError`, so it is already counted and shown as a failed call. No setting and **no off switch** (a switch that turns a security control off in production would be the hidden default the project forbids).
- One line added at each of the four call sites. No behaviour change when everything is as today.

Also a one-page table for the client, `docs/experiments/injection/LEAST-PRIVILEGE.md`: role, tools allowed, where it is enforced, what the experiment saw, and what it could not show.

## Tests (first, no network)

Each role: the allowed tools pass, any other tool in the request raises. Each role: an answer made of a `function_call`, an `mcp_call`, a `shell_call` and a made-up new type is refused with the role in the message and no content in the log; an answer of only messages passes; a researcher answer with `web_search_call` passes while a judge answer with one is refused. The four real call sites are exercised with a fake client that returns a function call (each ends as a model error, none returns data). The unchanged pipeline tests must still pass.

## Not done

No new attack experiment; no change to the harness; no change to the hosted search (it runs inside OpenAI and cannot be gated by us: said in the table). No gating of the page fetcher (already control 3, unchanged).

## Checks to state at close

Lateral spread: all four call sites guarded; the harness is separate and listed as such; the Kalshi, Odds and Telegram clients are not model calls and are out of scope. Causal depth: the two reasons above are both answered only in part: the control is now explicit and tested, but the experiment's "no effect observable" result is unchanged and is stated that way.
