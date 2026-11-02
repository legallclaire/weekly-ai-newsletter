from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from itertools import batched

from pydantic import BaseModel

from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import Paper, PaperScore, ScoredPaper
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import render_prompt

logger = logging.getLogger(__name__)


class PaperScoreBatch(BaseModel):
    scores: list[PaperScore]


class PaperScorer:
    """Asks the LLM for per-criterion scores; aggregation happens in PaperScore.total."""

    def __init__(self, llm: LLMClient, *, batch_size: int) -> None:
        self._llm = llm
        self._batch_size = batch_size

    def score(self, papers: Sequence[Paper]) -> list[ScoredPaper]:
        system = render_prompt("score_papers.md.j2")
        results: list[ScoredPaper] = []
        for batch in batched(papers, self._batch_size):
            prompt = json.dumps(
                [{"arxiv_id": p.arxiv_id, "title": p.title, "abstract": p.abstract} for p in batch],
                ensure_ascii=False,
                indent=2,
            )
            try:
                answer = self._llm.structured(
                    system=system, prompt=prompt, output_model=PaperScoreBatch
                )
            except LLMOutputError:
                logger.warning("Skipping a batch of %d papers: invalid LLM output", len(batch))
                continue
            pending = {paper.arxiv_id: paper for paper in batch}
            for score in answer.scores:
                paper = pending.pop(score.arxiv_id, None)
                if paper is not None:
                    results.append(ScoredPaper(paper=paper, score=score))
        return results
