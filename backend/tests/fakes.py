"""A stand-in for the OpenAI model, so tests never spend money or need a key."""

import asyncio

from app.research.model import ResearchModelError
from app.research.schemas import Angle, Citation, Plan, ResearchOutput, TextSegment, Usage


def make_segment(lines: list[tuple[str, str | None]]) -> TextSegment:
    """Builds answer text like OpenAI's: each line is '- fact ([site](url))' with a citation covering
    the bracketed part. A line given url None has no citation."""
    text, citations = "", []
    for fact, url in lines:
        line = f"- {fact}"
        if url:
            markup = f" ([{url.split('//')[1].split('/')[0]}]({url}))"
            start = len(text) + len(line) + 1  # skip the space before the opening bracket
            citations.append(Citation(url=url, title=f"Page {url}", start=start, end=start + len(markup) - 1))
            line += markup
        text += line + "\n"
    return TextSegment(text=text.rstrip("\n"), citations=citations)


class FakeModel:
    def __init__(self, angle_names=("Form", "Injuries"), fail=(), delay=0.05, lines=None, planner_usage=None):
        self.angle_names = list(angle_names)
        self.fail = set(fail)
        self.delay = delay
        self.lines = lines  # dict angle name -> list of (fact, url)
        self.planner_usage = planner_usage or Usage("gpt-5.4-mini", 1000, 0, 200)
        self.plan_calls = []
        self.research_calls = []
        self.running = 0
        self.max_running = 0

    async def plan(self, market, max_angles):
        self.plan_calls.append((market, max_angles))
        return Plan(angles=[Angle(name=n, question=f"What about {n}?") for n in self.angle_names]), self.planner_usage

    async def research(self, market, angle):
        self.research_calls.append(angle.name)
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            if angle.name in self.fail:
                raise ResearchModelError(f"Researcher call failed: boom for {angle.name}")
            lines = (self.lines or {}).get(angle.name) or [
                (f"{angle.name} fact one", f"https://{angle.name.lower()}.test/a"),
                (f"{angle.name} fact two", f"https://{angle.name.lower()}.test/b"),
            ]
            return ResearchOutput(segments=[make_segment(lines)], usage=Usage("gpt-5.4", 5000, 1000, 800, 2))
        finally:
            self.running -= 1
