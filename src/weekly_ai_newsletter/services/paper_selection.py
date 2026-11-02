from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from weekly_ai_newsletter.domain.models import ScoredPaper


@dataclass(frozen=True)
class SelectionRules:
    min_total: int
    min_novelty: int
    max_selected: int


def select_papers(scored: Iterable[ScoredPaper], rules: SelectionRules) -> list[ScoredPaper]:
    """Keep the best papers that are novel enough; an empty result is valid."""
    eligible = [
        candidate
        for candidate in scored
        if not candidate.score.is_incremental
        and candidate.score.novelty >= rules.min_novelty
        and candidate.score.total >= rules.min_total
    ]
    eligible.sort(
        key=lambda c: (
            -c.score.total,
            -(c.score.relevance + c.score.novelty),
            c.paper.arxiv_id,
        )
    )
    return eligible[: rules.max_selected]
