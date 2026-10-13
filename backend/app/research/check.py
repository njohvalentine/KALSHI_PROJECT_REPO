"""Checks each cited claim against the saved text of the page it was cited to.

The default verdict is the safe one. A claim is `supported` or `not_supported` only when the judge
quotes the page and the quote really is in the saved text; otherwise it becomes `could_not_check`.
A page we could not read, or that is only menus or a bot wall, can never make a claim
`not_supported`. Page text is untrusted: the judge has no tools, and a verdict that is not backed
by a quote from the page is thrown away, so a sentence on the page that tells the judge what to
answer achieves nothing.

One model call per page (all claims cited to that page together), so cost grows with pages."""

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.models import ClaimCheck, Run, SourcePage
from app.research.model import ResearchModelError, _today, openai_client, usage_from
from app.research.prompts import CHECKER_INSTRUCTIONS, PAGE_TAG, checker_input
from app.research.schemas import Usage, is_market_angle

log = logging.getLogger("app.research.check")

MIN_PAGE_CHARS = 200
MIN_QUOTE_CHARS = 10
MAX_QUOTES = 3
Verdict = Literal["supported", "not_supported", "could_not_check"]


class ClaimVerdict(BaseModel):
    claim_number: int
    verdict: Verdict
    quotes: list[str]  # required field (may be empty): one to three exact passages that together show the claim
    reason: str = ""


class Verdicts(BaseModel):
    verdicts: list[ClaimVerdict]


class ClaimJudge(Protocol):
    async def judge(
        self, game_title: str, page_url: str, page_title: str | None, page_text: str, cut: bool, claims: list[str]
    ) -> tuple[list[ClaimVerdict], Usage]: ...


class OpenAIClaimJudge:
    def __init__(self, settings: Settings, client=None):
        self._s = settings
        self._client = client or openai_client(settings)

    async def judge(self, game_title, page_url, page_title, page_text, cut, claims):
        try:
            response = await self._client.responses.parse(
                model=self._s.checker_model,
                instructions=CHECKER_INSTRUCTIONS.format(today=_today()),
                input=checker_input(game_title, page_url, page_title, page_text, cut, claims),
                text_format=Verdicts,
                reasoning={"effort": self._s.checker_reasoning_effort},
                max_output_tokens=self._s.checker_max_output_tokens,
                store=False,
            )
        except Exception as exc:
            raise ResearchModelError(f"Claim check call failed: {type(exc).__name__}: {exc}") from exc
        if response.output_parsed is None:
            raise ResearchModelError("The claim checker returned no usable answer")
        return response.output_parsed.verdicts, usage_from(response, self._s.checker_model)


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip().casefold()


def quote_is_on_page(quote: str, page_text: str) -> bool:
    """True if the quote (or every piece of it, when the judge joined passages with '...') is in the page."""
    pieces = [p for p in (_norm(p) for p in re.split(r"\.\.\.|…", quote)) if p]
    page = _norm(page_text)
    return bool(pieces) and all(len(p) >= MIN_QUOTE_CHARS and p in page for p in pieces)


def _numbers(text: str) -> set[str]:
    """Numbers in a text. In a dd/mm/yyyy date only the year counts: pages write the same date as
    '12 ottobre 2026' or 'Oct. 12', so day and month numbers cannot be compared as text."""
    text = re.sub(r"\b\d{1,2}/\d{1,2}/(\d{4})\b", r"\1", text.translate(_QUOTES))
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


CONTEXT_CHARS = 200


def quote_context(quote: str, page_text: str, radius: int = CONTEXT_CHARS) -> str:
    """The page text around each piece of a quote (radius characters either side), so a number that sits just
    outside the quote (a date in a heading, a round in a caption) still counts for the claim."""
    page = page_text.translate(_QUOTES)
    around = []
    for piece in re.split(r"\.\.\.|\u2026", quote.translate(_QUOTES)):
        words = piece.split()
        if not words:
            continue
        found = re.search(r"\s+".join(re.escape(w) for w in words), page, re.IGNORECASE)
        if found:
            around.append(page[max(found.start() - radius, 0): found.end() + radius])
    return " ".join(around)


def decide(verdict: ClaimVerdict | None, page_text: str, claim_text: str = "") -> tuple[str, str]:
    """Turns the judge's answer for one claim into the saved (verdict, reason). Anything unbacked is could_not_check.

    `page_text` must be exactly the text the judge was shown. Every number in the claim of a `supported`
    verdict must be in its quotes or in the page text right around them (CONTEXT_CHARS either side): real
    but unrelated quotes prove nothing, while a date in a heading just above the quote still counts."""
    if verdict is None:
        return "could_not_check", "The judge gave no answer for this claim."
    if verdict.verdict == "could_not_check":
        return "could_not_check", verdict.reason or "The judge could not find the claim on the page."
    quotes = [q.strip() for q in verdict.quotes if q.strip()]
    if not quotes or len(quotes) > MAX_QUOTES:
        return "could_not_check", f"The judge said {verdict.verdict} without one to {MAX_QUOTES} quotes from the page."
    if not all(quote_is_on_page(q, page_text) for q in quotes):
        return "could_not_check", f"The judge said {verdict.verdict}, but a quote was not found in the page."
    if verdict.verdict == "supported":
        near = " ".join(quotes) + " " + " ".join(quote_context(q, page_text) for q in quotes)
        if not _numbers(claim_text) <= _numbers(near):
            return "could_not_check", "The judge said supported, but the numbers of the claim are not in its quotes or right around them."
    return verdict.verdict, f'{verdict.reason} Quotes: ' + " / ".join(f'"{q}"' for q in quotes)


def unreadable_reason(status: str, detail: str | None, text: str | None) -> str | None:
    """Why a page cannot be checked at all (no model call), or None if it can be."""
    if status != "ok":
        return detail or f"The page could not be read ({status})."
    if not text or len(text) < MIN_PAGE_CHARS:
        return "The page text is too short to check against."
    return None


@dataclass
class PageJob:
    url: str
    title: str | None
    status: str  # the page's fetch_status
    detail: str | None
    text: str | None
    claims: list[tuple[int, int, str]] = field(default_factory=list)  # (finding_index, claim_index, claim text)


@dataclass
class CheckSummary:
    counts: dict[str, int] = field(default_factory=dict)
    usages: list[dict] = field(default_factory=list)
    skipped_existing: int = 0


def build_jobs(findings: list[dict], pages: dict[str, SourcePage]) -> dict[str, PageJob]:
    """Groups every sourced claim by the page it was cited to."""
    jobs: dict[str, PageJob] = {}
    for fi, finding in enumerate(findings):
        for ci, claim in enumerate(finding.get("claims", [])):
            if claim.get("kind") != "sourced":
                continue  # uncited lines are never checked and never go forward
            for source in claim.get("sources", []):
                url = source["url"]
                if url not in jobs:
                    page = pages.get(url)
                    jobs[url] = PageJob(
                        url, source.get("title") or (page.title if page else None),
                        page.fetch_status if page else "missing",
                        page.fetch_detail if page else "This page was not recorded for the run.",
                        page.page_text if page else None,
                    )
                if (fi, ci, claim["text"]) not in jobs[url].claims:
                    jobs[url].claims.append((fi, ci, claim["text"]))
    return jobs


async def check_run(engine, run_id: str, judge: ClaimJudge, settings: Settings) -> CheckSummary:
    """Checks every sourced claim of a finished run and saves one row per claim and page."""
    with DbSession(engine) as db:
        run = db.get(Run, run_id)
        if run is None or not run.result:
            raise ValueError(f"Run {run_id} has no result to check")
        findings, title = run.result["findings"], run.event_title
        pages = {p.url: p for p in db.scalars(select(SourcePage).where(SourcePage.run_id == run_id))}
        done = set(db.execute(
            select(ClaimCheck.finding_index, ClaimCheck.claim_index, ClaimCheck.source_url).where(ClaimCheck.run_id == run_id)
        ).all())

    summary = CheckSummary()
    rows: list[ClaimCheck] = []
    semaphore = asyncio.Semaphore(settings.check_concurrency)

    async def one_page(job: PageJob) -> None:
        todo = [c for c in job.claims if (c[0], c[1], job.url) not in done]
        summary.skipped_existing += len(job.claims) - len(todo)
        if not todo:
            return

        def save(results: list[tuple[str, str]]) -> None:
            for (fi, ci, _), (verdict, reason) in zip(todo, results):
                rows.append(ClaimCheck(run_id=run_id, finding_index=fi, claim_index=ci, source_url=job.url,
                                       verdict=verdict, reason=reason[:2000], model=settings.checker_model))
                summary.counts[verdict] = summary.counts.get(verdict, 0) + 1

        why = unreadable_reason(job.status, job.detail, job.text)
        if why:
            save([("could_not_check", why)] * len(todo))
            return
        cut = len(job.text) > settings.check_page_chars
        shown = PAGE_TAG.sub("[tag removed]", job.text[: settings.check_page_chars])  # exactly what the judge sees
        async with semaphore:
            try:
                verdicts, usage = await judge.judge(
                    title, job.url, job.title, shown, cut, [c[2] for c in todo]
                )
            except Exception as exc:  # one failed page must not lose the others; logged, and saved as could_not_check
                log.warning("Checking %s failed: %s", job.url, exc)
                save([("could_not_check", f"The check could not be run: {type(exc).__name__}")] * len(todo))
                return
        summary.usages.append(asdict(usage))
        numbers = [v.claim_number for v in verdicts]
        # A claim number answered twice has no trustworthy answer (the last one must not win silently).
        by_number = {v.claim_number: v for v in verdicts if numbers.count(v.claim_number) == 1}
        if sorted(numbers) != list(range(1, len(todo) + 1)):
            log.warning("The judge's answer for %s did not match its claims (%d answers for %d claims)",
                        job.url, len(verdicts), len(todo))
        save([decide(by_number.get(i), shown, todo[i - 1][2]) for i in range(1, len(todo) + 1)])

    await asyncio.gather(*(one_page(job) for job in build_jobs(findings, pages).values()))

    with DbSession(engine) as db:
        db.add_all(rows)
        db.commit()
    log.info("Run %s: checked %d claim(s): %s (%d already checked)", run_id, len(rows), summary.counts, summary.skipped_existing)
    return summary


def supported_claims(findings: list[dict], checks) -> list[dict]:
    """The claims that go forward to the forecasters: those with at least one page that supports them.
    Findings about odds or market prices (see is_market_angle) never go forward.

    `checks` is any iterable of objects with finding_index, claim_index, source_url and verdict."""
    supporting: dict[tuple[int, int], list[str]] = {}
    for c in checks:
        if c.verdict == "supported":
            supporting.setdefault((c.finding_index, c.claim_index), []).append(c.source_url)
    out = []
    for fi, finding in enumerate(findings):
        if is_market_angle(finding.get("kind"), finding.get("angle")):
            continue  # odds are market information, never evidence for the forecasters
        for ci, claim in enumerate(finding.get("claims", [])):
            if claim.get("kind") == "sourced" and (fi, ci) in supporting:
                out.append({"finding_index": fi, "claim_index": ci, "angle": finding.get("angle"),
                            "text": claim["text"], "supported_by": supporting[(fi, ci)]})
    return out
