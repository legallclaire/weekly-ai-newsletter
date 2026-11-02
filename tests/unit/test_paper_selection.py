from tests.factories import make_paper, make_score
from weekly_ai_newsletter.domain.models import ScoredPaper
from weekly_ai_newsletter.services.paper_selection import SelectionRules, select_papers

RULES = SelectionRules(min_total=45, min_novelty=6, max_selected=3)


def scored(
    arxiv_id: str,
    *,
    relevance: int = 7,
    novelty: int = 7,
    evidence: int = 7,
    depth: int = 7,
    practical_utility: int = 7,
    is_incremental: bool = False,
) -> ScoredPaper:
    score = make_score(
        arxiv_id,
        relevance=relevance,
        novelty=novelty,
        evidence=evidence,
        depth=depth,
        practical_utility=practical_utility,
        is_incremental=is_incremental,
    )
    return ScoredPaper(make_paper(arxiv_id), score)


def test_drops_incremental_low_novelty_and_low_total() -> None:
    papers = [
        scored("a", relevance=10, novelty=9, is_incremental=True),
        scored("b", relevance=10, novelty=5, evidence=10, depth=10, practical_utility=10),
        scored("c", relevance=5, novelty=6, evidence=5, depth=5, practical_utility=5),  # 37
        scored("d", relevance=8, novelty=8),  # 2*8 + 2*8 + 21 = 53
    ]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["d"]


def test_keeps_at_most_max_selected_sorted_by_total() -> None:
    papers = [scored(str(i), relevance=6 + i, novelty=7) for i in range(5)]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["4", "3", "2"]


def test_ties_broken_by_relevance_plus_novelty_then_id() -> None:
    papers = [
        scored("z", relevance=7, novelty=7, evidence=9),  # total 51, r+n 14
        scored("y", relevance=8, novelty=7, evidence=7),  # total 51, r+n 15
        scored("x", relevance=7, novelty=7, evidence=9),  # total 51, r+n 14
    ]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["y", "x", "z"]


def test_returns_empty_when_nothing_qualifies() -> None:
    assert select_papers([scored("a", relevance=3, novelty=3)], RULES) == []
