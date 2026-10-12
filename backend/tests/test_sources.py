import hashlib
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.research.sources import save_sources, source_rows
from tests.conftest import needs_db

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def claim(t, urls, kind=None):
    return {"text": t, "kind": kind or ("sourced" if urls else "uncited"), "sources": [{"url": u, "title": f"T {u}"} for u in urls]}


FINDINGS = [
    {"angle": "Form", "claims": [claim("A won 5 straight", ["https://a.test"]), claim("No source line", []), claim("No relevant information found.", [], "none")]},
    {"angle": "Odds", "claims": [claim("Odds favor A", ["https://a.test", "https://b.test"]), claim("A won 5 straight", ["https://a.test"])]},
]


def test_one_row_per_distinct_url_with_claims_merged_without_duplicates():
    rows = {r.url: r for r in source_rows("run1", FINDINGS, NOW)}
    assert set(rows) == {"https://a.test", "https://b.test"}
    assert rows["https://a.test"].content == "A won 5 straight\nOdds favor A"  # the repeated claim is listed once
    assert rows["https://b.test"].content == "Odds favor A"
    assert rows["https://a.test"].title == "T https://a.test" and rows["https://a.test"].retrieved_at == NOW


def test_hash_is_of_the_saved_content_and_stable():
    first = source_rows("r", FINDINGS, NOW)
    second = source_rows("r", FINDINGS, NOW)
    assert [r.content_hash for r in first] == [r.content_hash for r in second]
    assert first[0].content_hash == hashlib.sha256(first[0].content.encode()).hexdigest()


def test_nothing_is_saved_for_uncited_or_empty_results():
    assert source_rows("r", [{"angle": "x", "claims": [claim("no source", [])]}], NOW) == []
    assert source_rows("r", [], NOW) == []


@needs_db
def test_rows_are_stored_for_the_run(fresh_db):
    from alembic import command

    from tests.conftest import alembic_config

    command.upgrade(alembic_config(), "head")
    with DbSession(fresh_db) as db:
        assert save_sources(db, "run1", FINDINGS, NOW) == 2
    with fresh_db.connect() as conn:
        rows = conn.execute(text("SELECT url, run_id, length(content_hash) FROM source_pages ORDER BY url")).all()
    assert rows == [("https://a.test", "run1", 64), ("https://b.test", "run1", 64)]
