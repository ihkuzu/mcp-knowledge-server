import pytest

from mcpkb.config import ROOT
from mcpkb.docs import DocIndex, split_sections, stem, tokenize


@pytest.fixture(scope="module")
def index():
    return DocIndex(ROOT / "data" / "docs")


def test_split_sections_keeps_title_and_headings():
    chunks = split_sections("x", "# Title\n\nintro\n\n## One\ntext one\n## Two\ntext two\n")
    assert [(c.title, c.section) for c in chunks] == [("Title", "Title"), ("Title", "One"), ("Title", "Two")]
    assert chunks[1].text == "text one"


def test_empty_sections_are_skipped():
    assert [c.section for c in split_sections("x", "# T\n## Empty\n\n## Full\nbody")] == ["Full"]


def test_stem_and_stopwords():
    assert stem("returns") == "return"
    assert stem("invoices") == stem("invoice")
    assert stem("policies") == stem("policy")
    assert tokenize("How many days are there?") == ["day"]


def test_keyword_query_finds_section(index):
    hit = index.search("hygiene seal earbuds", k=1)[0]
    assert (hit.doc, hit.section) == ("returns-policy", "Hygiene products")


def test_results_are_sorted_and_limited(index):
    hits = index.search("return refund", k=3)
    assert len(hits) == 3
    assert [h.score for h in hits] == sorted([h.score for h in hits], reverse=True)


def test_min_score_filters_weak_matches(index):
    assert index.search("parental leave", min_score=4.0) == []
    assert index.search("zzzz qqqq") == []


def test_list_docs(index):
    docs = {d["name"]: d for d in index.list_docs()}
    assert len(docs) == 10
    assert docs["incident-response"]["title"] == "Incident Response"
    assert "Postmortems" in docs["incident-response"]["sections"]


@pytest.mark.parametrize("name", ["../pyproject", "returns-policy.md", "/etc/passwd", "Returns-Policy", "missing", ""])
def test_read_rejects_unknown_or_unsafe_names(index, name):
    with pytest.raises(KeyError):
        index.read(name)


def test_read_returns_markdown(index):
    assert index.read("onboarding").startswith("# Onboarding")
