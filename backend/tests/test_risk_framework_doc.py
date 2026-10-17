"""The proposed numbers in docs/RISK-FRAMEWORK.md must agree with the comments of .env.example (they cannot drift apart)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "RISK-FRAMEWORK.md").read_text()
ENV = (ROOT / ".env.example").read_text()


def doc_rows():
    for line in DOC.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`(ORDER_[A-Z_]+)`(?: and `[A-Z_]+`)?", cells[2]) if len(cells) >= 4 else None
        if match:
            yield match.group(1), cells[1]


def test_every_proposed_value_in_the_document_is_in_the_comment_of_its_setting():
    rows = dict(doc_rows())
    assert {"ORDER_MAX_COST_USD", "ORDER_MAX_DAY_COST_USD", "ORDER_PAUSE_DAY_LOSS_USD", "ORDER_PAUSE_TOTAL_LOSS_USD"} <= set(rows)
    for setting, proposed in rows.items():
        line = next((l for l in ENV.splitlines() if l.lstrip("# ").startswith(setting + "=")), None)
        assert line is not None, f"{setting} is not in .env.example"
        number = re.match(r"(\d+)", proposed).group(1)
        assert re.search(rf"Proposed {number}\b", line), f"{setting}: the document proposes {number}, the comment says: {line}"


def test_the_document_says_it_is_a_proposal_and_names_the_arithmetic():
    assert "a proposal for the client's approval" in DOC and "2.15 dollars a day" in DOC and "NO BET is the default answer" in DOC
