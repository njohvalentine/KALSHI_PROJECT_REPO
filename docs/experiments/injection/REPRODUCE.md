# Reproducing the injection experiment

Everything below runs from `backend/` with the app's settings in the environment (the OpenAI key is read from the environment and is never written to any file).

```
uv run --no-sync python -m experiments.injection list                 # the 20 attacks and 4 clean pages
uv run --no-sync python -m experiments.injection plan --repeats 3 --forecasters 1      # the number of runs per entry point, no cost
uv run --no-sync python -m experiments.injection run --repeats 3 --forecasters 1 --cap 40   # the full run; resumes from the log if stopped
uv run --no-sync python -m experiments.injection report --runs ../docs/experiments/injection/runs.jsonl --out ../docs/experiments/injection/REPORT-RESULTS.md
```

What is kept, next to the log (`runs.jsonl`):
- `runs-CONFIG.json`: the code commit, the models and reasoning settings, every prompt each condition uses (researcher, researcher with the hostile-instruction rule, judge, forecaster), the tool definitions, the fake market prices, the game, all 27 pages as HTML, and the attack definitions.
- `runs.jsonl`: one record per run: condition, attack, entry point, repeat, the complete model inputs and outputs, the researcher's tool transcript, the claims with their verdicts, the forecast, the order step, every fake tool call and every request that reached the fake servers, which control stopped something, token usage per call, the model version OpenAI reports, and the cost.
- `REPORT-RESULTS.md` and its `.csv`: the tables, produced by `report` from the log alone.
- The code: `backend/experiments/injection/` (corpus, harness, analysis) and its tests `backend/tests/test_injection_experiment.py` (no network, no cost).

What reproducing means here: the same pages, code, settings and model versions give a result of the same kind, not identical text, because the models do not answer the same way twice. The pilot (`runs-pilot.jsonl`, 92 runs) and a stopped first attempt (`runs-stopped-before-adjustments.jsonl`, 327 runs, truncated logs, not used for any result) are kept for the record.

## After the experiment: the app changed (FEAT-20261023-1129)

The results are for commit `29ca4e6`. Since then the app's researcher prompt carries the hostile-instruction rule that condition PR tested (the exact wording is in `runs-CONFIG.json`; a test checks that the app's prompt equals it). In the harness, condition P is now built as the app's prompt **without** that rule, which is the app as it was when the experiment ran, and PR is the app's prompt as it is now. To reproduce the numbers exactly, either use the harness as it is (P and PR keep their meaning) or check out commit `29ca4e6`.
