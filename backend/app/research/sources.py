"""Records every page a run cited, as the start of the frozen record that fair backtests need.

What is saved per page: the link, the title, the time, and the claims this page was cited for.
It is NOT a copy of the page: OpenAI's citations carry only a link and a title (and where in the
answer they sit), no text from the page. Saving page text would need our own fetch (later, only if
the backtests need it)."""

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session as DbSession

from app.models import SourcePage


def source_rows(run_id: str, findings: list[dict], retrieved_at: datetime) -> list[SourcePage]:
    pages: dict[str, dict] = {}
    for finding in findings:
        for claim in finding["claims"]:
            for source in claim["sources"]:
                page = pages.setdefault(source["url"], {"title": source.get("title") or None, "claims": []})
                if not page["title"]:
                    page["title"] = source.get("title") or None
                if claim["text"] not in page["claims"]:
                    page["claims"].append(claim["text"])
    rows = []
    for url, page in pages.items():
        content = "\n".join(page["claims"])
        rows.append(
            SourcePage(
                run_id=run_id,
                url=url,
                title=page["title"],
                retrieved_at=retrieved_at,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
            )
        )
    return rows


def save_sources(db: DbSession, run_id: str, findings: list[dict], retrieved_at: datetime) -> int:
    rows = source_rows(run_id, findings, retrieved_at)
    db.add_all(rows)
    db.commit()
    return len(rows)
