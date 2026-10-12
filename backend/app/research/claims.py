"""Turns a researcher's answer into claims with the links the search tool actually cited.

Source links come only from the tool's url_citation annotations, never from URLs the model typed
in its text. OpenAI also writes the citation as link markup inside the text; that markup is cut out
of the claim text and kept as structured sources instead.
"""

import re
from dataclasses import dataclass

from app.research.schemas import Citation, TextSegment

NO_FINDINGS = "no relevant information found"


@dataclass
class Claim:
    text: str
    kind: str  # "sourced", "uncited" (no citation on the line) or "none" (researcher found nothing)
    sources: list[dict]

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "sources": self.sources}


def _plain(text: str) -> str:
    """Removes markdown emphasis the model adds (bold, italics, code), keeping the words."""
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)  # bold
    text = re.sub(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])", r"\1", text)  # *italic*
    return text.replace("`", "").replace("**", "")  # code ticks and any unbalanced bold marker


def _clean(text: str) -> str:
    text = _plain(text)
    text = re.sub(r"\(\s*\)", "", text)  # parentheses left empty after cutting the link markup
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _cut(line: str, line_start: int, citations: list[Citation]) -> str:
    """Removes the citation markup (given as ranges in the whole text) from one line."""
    out, pos = [], 0
    for c in sorted(citations, key=lambda c: c.start):
        a = max(c.start - line_start, pos)
        b = min(c.end - line_start, len(line))
        if a >= b:
            continue
        out.append(line[pos:a])
        pos = b
    out.append(line[pos:])
    return "".join(out)


def build_claims(segments: list[TextSegment]) -> tuple[list[Claim], int]:
    """Returns the claims and how many citation ranges had to be ignored as out of bounds."""
    claims: list[Claim] = []
    bad = 0
    for segment in segments:
        text = segment.text
        valid = []
        for c in segment.citations:
            if 0 <= c.start < c.end <= len(text):
                valid.append(c)
            else:
                bad += 1  # index conventions are unverified live; never guess a position
        pos = 0
        for line in text.split("\n"):
            start, end = pos, pos + len(line)
            pos = end + 1
            if not line.lstrip().startswith("- "):
                continue
            mine = [c for c in valid if start <= c.start < end]
            body = _clean(_cut(line, start, mine).lstrip()[2:])
            if not body:
                continue
            sources, seen = [], set()
            for c in mine:
                if c.url not in seen:
                    seen.add(c.url)
                    sources.append({"url": c.url, "title": c.title})
            if body.lower().rstrip(".").startswith(NO_FINDINGS):
                claims.append(Claim(body, "none", []))
            else:
                claims.append(Claim(body, "sourced" if sources else "uncited", sources))
    return claims, bad
