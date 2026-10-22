"""Everything needed to reproduce a run, written next to the log: the code version, the model settings (never a key), every prompt each condition uses, the tool definitions and the pages."""

import json
import subprocess
from pathlib import Path

from app.research.prompts import FRAMINGS
from experiments.injection import corpus, stages, variants
from experiments.injection.canary import CANARY_TOOLS
from experiments.injection.conditions import CONDITIONS, CONTROLS, HARDENED_RESEARCHER


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def snapshot(settings, forecasters: int) -> dict:
    s = settings
    return {
        "code_commit": _git("rev-parse", "HEAD"), "uncommitted_changes": bool(_git("status", "--porcelain", "--", "experiments", "app")),
        "today_in_prompts": stages.TODAY, "forecasters_in_experiment": forecasters, "app_forecaster_count": s.forecaster_count,
        "models": {"researcher": s.researcher_model, "checker": s.checker_model, "forecaster": s.forecaster_model},
        "reasoning_effort": {"researcher": s.research_reasoning_effort, "checker": s.checker_reasoning_effort, "forecaster": s.forecaster_reasoning_effort},
        "max_output_tokens": {"researcher": s.researcher_max_output_tokens, "checker": s.checker_max_output_tokens, "forecaster": s.forecaster_max_output_tokens},
        "check_page_chars": s.check_page_chars, "edge_min": s.edge_min, "fake_market_asks": {k: str(v) for k, v in stages.FAKE_ASKS.items()},
        "controls": CONTROLS, "conditions": {c: sorted(on) for c, on in CONDITIONS.items()}, "hardened_researcher_conditions": sorted(HARDENED_RESEARCHER),
        "prompts": {
            "researcher": stages.researcher_instructions(), "researcher_hardened": stages.researcher_instructions(variants.RESEARCHER_RULE),
            "judge": {f"control1_{'on' if on1 else 'off'}_control4_{'on' if on4 else 'off'}": variants.judge_instructions(stages.TODAY, on1, on4) for on1 in (True, False) for on4 in (True, False)},
            "forecaster": {f"{framing[0]}_control1_{'on' if on1 else 'off'}_control4_{'on' if on4 else 'off'}": variants.forecaster_instructions(corpus.GAME, stages.TODAY, framing, on1, on4)
                           for framing in FRAMINGS for on1 in (True, False) for on4 in (True, False)},
        },
        "tools": {"researcher": [stages.SEARCH_TOOL, stages.READ_TOOL], "canary": CANARY_TOOLS},
        "game": {"title": corpus.GAME.title, "outcomes": corpus.GAME.outcomes, "market_tickers": corpus.GAME.market_tickers},
        "pages": {p.path: p.html for p in list(corpus.BASE) + [a.page for a in corpus.ATTACKS] + [c for c, _ in corpus.CLEAN]},
        "attacks": [{"id": a.id, "class": a.cls, "summary": a.summary, "goal": a.goal, "entries": a.entries, "planted_claim": a.planted_claim, "true_claim": a.true_claim, "fact_line": a.fact_line} for a in corpus.ATTACKS],
    }


def write(path: Path, settings, forecasters: int) -> None:
    path.write_text(json.dumps(snapshot(settings, forecasters), indent=1, ensure_ascii=False))
