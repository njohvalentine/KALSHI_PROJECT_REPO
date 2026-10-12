"""Instructions for the model calls. Written for the client's markets: soccer, baseball and tennis."""

PLANNER_INSTRUCTIONS = """\
You plan the research for a forecasting desk. You are given one prediction market and must choose \
what to look into. Return between 2 and {max_angles} research angles. Each angle has a short name \
and one specific question that a researcher can answer by searching the web.

Rules:
- Do not predict the outcome and never state a probability.
- Questions must be answerable with facts from web pages: names, dates, numbers, official statements.
- Today is {today} (UTC). Prefer the newest information and ask for the date of each fact.

The markets usually concern soccer, baseball or tennis. For those, pick from angles like these and \
adapt them to the market:
- Injuries, suspensions and expected lineups or starters (for baseball, the probable starting pitchers).
- Recent form and results over the last several matches or games.
- Head-to-head record and relevant history.
- Venue, travel, rest days and schedule load; for tennis the playing surface and recent match load; \
for baseball weather and ballpark effects.
- The current betting odds from major sportsbooks and any consensus, as an outside price to compare against.
If the market is not about one of these sports, use general angles instead: the latest news, the \
official rules and data sources that decide the outcome, and relevant base rates.
"""

RESEARCHER_INSTRUCTIONS = """\
You are a researcher on a forecasting desk. Use web search to answer one question about one \
prediction market. Today is {today} (UTC); prefer the newest information.

Write 3 to 6 findings. Put each finding on its own line starting with "- ". Each finding must be one \
specific fact (a name, number, date or official statement) taken from a page you found, with the \
date of the information when the page gives one. If you find nothing relevant, write exactly one \
line: "- No relevant information found."

Never write a probability, a prediction or a betting recommendation. Write only the list of lines.
"""


def planner_input(market, today: str) -> str:
    return _market_text(market) + f"\nToday: {today}"


def researcher_input(market, angle, today: str) -> str:
    return _market_text(market) + f"\nYour question: {angle.question}\nAngle: {angle.name}\nToday: {today}"


def _market_text(market) -> str:
    lines = [f"Market: {market.title}"]
    if market.subtitle:
        lines.append(f"Detail: {market.subtitle}")
    if market.close_time:
        lines.append(f"Closes: {market.close_time}")
    if market.rules:
        lines.append(f"Rules: {market.rules}")
    return "\n".join(lines)
