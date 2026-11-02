from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import ScoredPaper, SelectedPaper
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt

logger = logging.getLogger(__name__)


class PaperWriteup(BaseModel):
    arxiv_id: str
    summary: str
    why_selected: str


class PaperWriteupBatch(BaseModel):
    writeups: list[PaperWriteup]


class PaperWriter:
    def __init__(self, llm: LLMClient, *, language: str) -> None:
        self._llm = llm
        self._language = language

    def write(self, selected: Sequence[ScoredPaper]) -> list[SelectedPaper]:
        if not selected:
            return []
        system = render_prompt("write_papers.md.j2", language=LANGUAGE_NAMES[self._language])
        prompt = json.dumps(
            [
                {
                    "arxiv_id": c.paper.arxiv_id,
                    "title": c.paper.title,
                    "abstract": c.paper.abstract,
                    "scores": c.score.model_dump(exclude={"arxiv_id", "rationale"}),
                    "curator_rationale": c.score.rationale,
                }
                for c in selected
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=PaperWriteupBatch)
        writeups = {w.arxiv_id: w for w in answer.writeups}
        missing = [c.paper.arxiv_id for c in selected if c.paper.arxiv_id not in writeups]
        if len(missing) == len(selected):
            raise LLMOutputError(f"missing write-ups for {', '.join(missing)}")
        if missing:
            logger.warning("Dropping papers without a write-up: %s", ", ".join(missing))
        return [
            SelectedPaper(
                paper=c.paper,
                score=c.score,
                summary=writeups[c.paper.arxiv_id].summary,
                why_selected=writeups[c.paper.arxiv_id].why_selected,
            )
            for c in selected
            if c.paper.arxiv_id in writeups
        ]
