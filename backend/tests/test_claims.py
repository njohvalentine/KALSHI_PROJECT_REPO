import pytest

from app.research.claims import build_claims
from app.research.schemas import Citation, TextSegment
from tests.fakes import make_segment


def test_citation_markup_is_cut_and_sources_attached_per_line():
    seg = make_segment([("Star striker out for three weeks", "https://a.test/1"), ("Won 4 of last 5", "https://b.test/2")])
    claims, bad = build_claims([seg])
    assert bad == 0
    assert [c.text for c in claims] == ["Star striker out for three weeks", "Won 4 of last 5"]
    assert [c.sources[0]["url"] for c in claims] == ["https://a.test/1", "https://b.test/2"]
    assert all(c.kind == "sourced" for c in claims)


def test_citation_on_the_last_character_of_a_line_belongs_to_that_line():
    text = "- First fact (a)\n- Second fact"
    seg = TextSegment(text=text, citations=[Citation("https://a.test", "A", text.index("(a)"), text.index("(a)") + 3)])
    claims, _ = build_claims([seg])
    assert claims[0].sources and claims[0].text == "First fact"
    assert claims[1].sources == [] and claims[1].kind == "uncited"


def test_parentheses_left_behind_by_a_citation_range_are_tidied():
    text = "- Rain is forecast for Saturday ([bbc.com](https://bbc.test))."
    a = text.index("[bbc.com]")  # the range excludes the surrounding parentheses
    seg = TextSegment(text=text, citations=[Citation("https://bbc.test", "BBC", a, text.index("))." ) + 1)])
    (claim,), _ = build_claims([seg])
    assert claim.text == "Rain is forecast for Saturday." and claim.kind == "sourced"


def test_out_of_range_citations_are_ignored_and_counted_never_guessed():
    text = "- A fact"
    seg = TextSegment(text=text, citations=[Citation("https://a.test", "A", 3, 999), Citation("https://b.test", "B", -1, 2), Citation("https://c.test", "C", 5, 5)])
    claims, bad = build_claims([seg])
    assert bad == 3 and claims[0].kind == "uncited" and claims[0].sources == []


def test_duplicate_urls_in_one_line_are_listed_once():
    seg = make_segment([("Fact", "https://a.test/1")])
    t = seg.text
    extra = Citation("https://a.test/1", "dup", t.index("(["), t.index("(") + 2)
    (claim,), _ = build_claims([TextSegment(text=t, citations=seg.citations + [extra])])
    assert [s["url"] for s in claim.sources] == ["https://a.test/1"]


def test_no_findings_line_and_preamble_and_empty_input():
    claims, _ = build_claims([TextSegment(text="Here is what I found:\n- No relevant information found.")])
    assert [(c.kind, c.sources) for c in claims] == [("none", [])]
    assert build_claims([TextSegment(text="Nothing useful.")]) == ([], 0)
    assert build_claims([]) == ([], 0)


def test_non_ascii_text_is_handled():
    seg = make_segment([("Équipe A: Müller blessé — retour incertain", "https://a.test/é")])
    (claim,), bad = build_claims([seg])
    assert claim.text == "Équipe A: Müller blessé — retour incertain" and bad == 0 and claim.kind == "sourced"


@pytest.mark.parametrize("raw,expected", [
    ("Said on **10/10/2026** that the break helped", "Said on 10/10/2026 that the break helped"),
    ("The **28-man squad list on 11/10/2026** names **Montipo** and **Haps**", "The 28-man squad list on 11/10/2026 names Montipo and Haps"),
    ("Won *four* of the last five", "Won four of the last five"),
    ("Kickoff `18:30` local", "Kickoff 18:30 local"),
    ("Unbalanced **bold marker here", "Unbalanced bold marker here"),
    ("Score was 2 * 1 on aggregate", "Score was 2 * 1 on aggregate"),  # a lone asterisk is kept
    ("Uses __underscores__ for bold", "Uses underscores for bold"),
    ("snake_case_name stays", "snake_case_name stays"),
])
def test_markdown_emphasis_is_removed_from_claim_text(raw, expected):
    (claim,), _ = build_claims([TextSegment(text="- " + raw)])
    assert claim.text == expected and "**" not in claim.text


def test_bold_around_a_citation_is_cleaned_too():
    seg = make_segment([("**Venezia** lost 0-2 to Lazio", "https://a.test/x")])
    (claim,), _ = build_claims([seg])
    assert claim.text == "Venezia lost 0-2 to Lazio" and claim.sources[0]["url"] == "https://a.test/x"
