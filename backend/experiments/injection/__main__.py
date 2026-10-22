"""python -m experiments.injection list | plan | pilot | run | report   (run from backend/ with the app's settings in the environment)"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from experiments.injection import analysis, corpus, runner
from experiments.injection.conditions import CONDITIONS

PILOT_ATTACKS = ["I1-1", "I2-1", "I3-1", "I4-1", "I4-2", "I5-1"]  # one or two of each class
DEFAULT_OUT = Path("../docs/experiments/injection")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="experiments.injection")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print the attack list")
    for name in ("plan", "pilot", "run"):
        s = sub.add_parser(name)
        s.add_argument("--attacks", default="all" if name != "pilot" else ",".join(PILOT_ATTACKS))
        s.add_argument("--conditions", default=",".join(CONDITIONS))
        s.add_argument("--e2e-conditions", default="B0,P" if name == "pilot" else ",".join(CONDITIONS), help="the conditions in which the costly end-to-end runs are done")
        s.add_argument("--repeats", type=int, default=1 if name == "pilot" else 3)
        s.add_argument("--forecasters", type=int, default=1 if name == "pilot" else 3)
        s.add_argument("--cap", type=float, default=40.0 if name == "run" else 8.0, help="stop when the model cost reaches this many USD")
        s.add_argument("--workers", type=int, default=4)
        s.add_argument("--out", default=str(DEFAULT_OUT / ("runs-pilot.jsonl" if name == "pilot" else "runs.jsonl")))
    r = sub.add_parser("report")
    r.add_argument("--runs", default=str(DEFAULT_OUT / "runs.jsonl"))
    r.add_argument("--out", default=str(DEFAULT_OUT / "REPORT-RESULTS.md"))
    a = p.parse_args(argv)

    if a.cmd == "list":
        print(corpus.describe())
        return 0
    if a.cmd == "report":
        runs = analysis.load(Path(a.runs))
        Path(a.out).write_text(analysis.report(runs))
        analysis.write_csv(runs, Path(a.out).with_suffix(".csv"))
        print(f"Report written to {a.out}")
        return 0
    attacks = [x.id for x in corpus.ATTACKS] if a.attacks == "all" else a.attacks.split(",")
    unknown = [x for x in attacks if x not in corpus.ATTACKS_BY_ID] + [c for c in a.conditions.split(",") + a.e2e_conditions.split(",") if c not in CONDITIONS]
    if unknown:
        print(f"Error: unknown name(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    specs = runner.plan(attacks, a.conditions.split(","), a.e2e_conditions.split(","), a.repeats)
    if a.cmd == "plan":
        print(f"{len(specs)} runs: " + ", ".join(f"{e}={sum(1 for s in specs if s.entry == e)}" for e in ("e2e", "judge", "forecaster")))
        return 0
    from app.config import SettingsError, load_settings
    from app.research.model import openai_client

    try:
        settings = load_settings(os.environ)
    except SettingsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    state = asyncio.run(runner.run_all(openai_client(settings), settings, specs, out, a.cap, a.workers, a.forecasters, log_line=lambda s: print(s, file=sys.stderr)))
    return 1 if state["stopped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
