from tests.factories import make_paper
from weekly_ai_newsletter.config import PaperKeywords
from weekly_ai_newsletter.services.keyword_filter import KeywordFilter
from weekly_ai_newsletter.services.text import keyword_pattern, truncate

KEYWORDS = PaperKeywords(
    title_weight=2.0,
    positive={"agent": 3, "rag": 3, "quantization": 2},
    negative={"medical imaging": 5},
)


def test_pattern_matches_plurals_and_ignores_case_but_respects_word_boundaries() -> None:
    pattern = keyword_pattern("agent")
    assert pattern.search("LLM Agents in the wild")
    assert not pattern.search("reagent chemistry")
    assert not keyword_pattern("rag").search("ragged arrays")


def test_title_matches_weigh_more_than_abstract_matches() -> None:
    keyword_filter = KeywordFilter(KEYWORDS)
    in_title = make_paper(title="Agents for science", abstract="We study things.")
    in_abstract = make_paper(title="A study", abstract="We build an agent.")
    assert keyword_filter.score(in_title) == 6.0
    assert keyword_filter.score(in_abstract) == 3.0


def test_negative_terms_subtract() -> None:
    paper = make_paper(title="RAG for medical imaging", abstract="")
    assert KeywordFilter(KEYWORDS).score(paper) == 2 * 3 - 2 * 5


def test_top_keeps_positive_scores_sorted_and_limited() -> None:
    papers = [
        make_paper("2610.00003", title="Quantization", abstract=""),
        make_paper("2610.00001", title="Agent RAG", abstract=""),
        make_paper("2610.00002", title="Unrelated topic", abstract=""),
        make_paper("2610.00004", title="Agent", abstract=""),
    ]
    top = KeywordFilter(KEYWORDS).top(papers, limit=2)
    assert [p.arxiv_id for p in top] == ["2610.00001", "2610.00004"]


def test_truncate_adds_ellipsis_only_when_needed() -> None:
    assert truncate("short", 10) == "short"
    assert truncate("abcdefghijkl", 5) == "abcd…"
