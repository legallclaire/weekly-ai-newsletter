from __future__ import annotations

from collections.abc import Iterable

from weekly_ai_newsletter.config import PaperKeywords
from weekly_ai_newsletter.domain.models import Paper
from weekly_ai_newsletter.services.text import keyword_pattern


class KeywordFilter:
    """Cheap, deterministic relevance pre-filter run before any LLM call."""

    def __init__(self, keywords: PaperKeywords) -> None:
        self._title_weight = keywords.title_weight
        self._terms = [
            (keyword_pattern(term), weight) for term, weight in keywords.positive.items()
        ]
        self._terms += [
            (keyword_pattern(term), -weight) for term, weight in keywords.negative.items()
        ]

    def score(self, paper: Paper) -> float:
        total = 0.0
        for pattern, weight in self._terms:
            if pattern.search(paper.title):
                total += weight * self._title_weight
            if pattern.search(paper.abstract):
                total += weight
        return total

    def top(self, papers: Iterable[Paper], limit: int) -> list[Paper]:
        scored = [(self.score(paper), paper) for paper in papers]
        relevant = [(score, paper) for score, paper in scored if score > 0]
        relevant.sort(key=lambda pair: (-pair[0], pair[1].arxiv_id))
        return [paper for _, paper in relevant[:limit]]
