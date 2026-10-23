"""The matrix of runs, the cost cap, the log. A run that is already in the log is skipped, so a stopped run can be continued."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.research.pricing import cost_usd
from experiments.injection import corpus, stages
from experiments.injection.conditions import CONDITIONS, HARDENED_RESEARCHER
from experiments.injection.labels import CURRENT_APP

CLEAN_E2E = {f"K{i}": page for i, (page, _) in enumerate(corpus.CLEAN, 1)}
STOP_AFTER_ERRORS = 5  # in a row: most likely no credit or no network; stop and say so


@dataclass(frozen=True)
class RunSpec:
    attack: str  # an attack id, K1..K4 (clean page in the slot), K0 (clean forecaster run) or K0j (clean judge run)
    entry: str
    cond: str
    rep: int

    @property
    def key(self) -> str:
        return f"{self.attack}|{self.entry}|{self.cond}|{self.rep}"


def plan(attacks: list[str], conds: list[str], e2e_conds: list[str], repeats: int) -> list[RunSpec]:
    """Every attack at each of its entry points, plus the clean references, for each condition and repeat. e2e runs only in `e2e_conds` (the costly stage)."""
    specs = []
    for rep in range(1, repeats + 1):
        for cond in conds:
            if cond in HARDENED_RESEARCHER:  # P plus a researcher rule: only the researcher stage differs from P, so only the end-to-end runs are done
                if cond in e2e_conds:
                    specs += [RunSpec(aid, "e2e", cond, rep) for aid in attacks if "e2e" in corpus.ATTACKS_BY_ID[aid].entries]
                    specs += [RunSpec(k, "e2e", cond, rep) for k in CLEAN_E2E]
                continue
            if cond in CURRENT_APP:  # the label measurement: the judge is the same as in P, so only the end-to-end and forecaster entries are run
                for aid in attacks:
                    for entry in corpus.ATTACKS_BY_ID[aid].entries:
                        if entry == "forecaster" or (entry == "e2e" and cond in e2e_conds):
                            specs.append(RunSpec(aid, entry, cond, rep))
                specs.append(RunSpec("K0", "forecaster", cond, rep))
                if cond in e2e_conds:
                    specs += [RunSpec(k, "e2e", cond, rep) for k in CLEAN_E2E]
                continue
            for aid in attacks:
                for entry in corpus.ATTACKS_BY_ID[aid].entries:
                    if entry != "e2e" or cond in e2e_conds:
                        specs.append(RunSpec(aid, entry, cond, rep))
            specs += [RunSpec("K0", "forecaster", cond, rep), RunSpec("K0j", "judge", cond, rep)]
            if cond in e2e_conds:
                specs += [RunSpec(k, "e2e", cond, rep) for k in CLEAN_E2E]
    return specs


def _resolve(spec: RunSpec) -> tuple[corpus.Page | None, dict]:
    if spec.attack in corpus.ATTACKS_BY_ID:
        a = corpus.ATTACKS_BY_ID[spec.attack]
        return a.page, {"planted": a.planted_claim, "true_claim": a.true_claim, "fact_line": a.fact_line}
    if spec.attack in CLEAN_E2E:
        return CLEAN_E2E[spec.attack], {}
    if spec.attack == "K0j":
        return corpus.BASE[0], {"true_claim": "Captain Jonas Brandt is fit and is expected to start."}
    return None, {}


async def run_spec(client, settings, spec: RunSpec, forecasters: int) -> dict:
    ctx = stages.Ctx(client, settings, spec.cond, CONDITIONS[spec.cond], forecasters=forecasters)
    slot, kw = _resolve(spec)
    try:
        rec = await stages.run_entry(ctx, spec.entry, slot, **kw)
    except Exception as exc:  # one failed run must not stop the others; it is logged and left out of the rates
        rec = {"entry": spec.entry, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "tool_calls": ctx.log.tool_calls, "fetches": ctx.log.fetches, "defenses": ctx.log.defenses}
    costs = [cost_usd(u) for u in ctx.usages]
    models = sorted({u.model for u in ctx.usages})
    usage = [{"model": u.model, "input_tokens": u.input_tokens, "cached_tokens": u.cached_tokens, "output_tokens": u.output_tokens} for u in ctx.usages]
    return {"key": spec.key, "attack": spec.attack, "cond": spec.cond, "rep": spec.rep, "usd": float(sum(c for c in costs if c is not None)),
            "unpriced": any(c is None for c in costs), "models": models, "models_seen": sorted(ctx.models_seen), "usage": usage, **rec}


async def run_all(client, settings, specs: list[RunSpec], out: Path, cap_usd: float, concurrency: int = 4, forecasters: int = 3, log_line=print) -> dict:
    done = {json.loads(line)["key"]: json.loads(line) for line in out.read_text().splitlines() if line.strip()} if out.exists() else {}
    todo = [s for s in specs if s.key not in done]
    spent = sum(r.get("usd", 0) for r in done.values())
    log_line(f"{len(specs)} runs planned, {len(done)} already in the log, {len(todo)} to run; spent so far {spent:.2f} USD, cap {cap_usd:.2f} USD")
    state = {"spent": spent, "errors": 0, "stopped": None, "done": 0}
    sem = asyncio.Semaphore(concurrency)

    async def one(spec: RunSpec) -> None:
        async with sem:
            if state["stopped"]:
                return
            if state["spent"] >= cap_usd:
                state["stopped"] = f"the cost cap of {cap_usd:.2f} USD was reached"
                return
            rec = await run_spec(client, settings, spec, forecasters)
            state["spent"] += rec["usd"]
            state["done"] += 1
            state["errors"] = state["errors"] + 1 if rec.get("error") else 0
            with out.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            if state["errors"] >= STOP_AFTER_ERRORS:
                state["stopped"] = f"{STOP_AFTER_ERRORS} runs in a row failed (last: {rec.get('error')})"
            if state["done"] % 10 == 0:
                log_line(f"{state['done']} of {len(todo)} runs done, {state['spent']:.2f} USD")

    await asyncio.gather(*(one(s) for s in todo))
    log_line(f"finished {state['done']} runs, {state['spent']:.2f} USD" + (f"; STOPPED: {state['stopped']}" if state["stopped"] else ""))
    return state
