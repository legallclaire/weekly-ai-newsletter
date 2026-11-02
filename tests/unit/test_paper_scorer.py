import json

from pydantic import BaseModel

from tests.factories import make_paper, make_score
from tests.fakes import FakeLLM
from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.services.paper_scorer import PaperScoreBatch, PaperScorer


def score_every_paper(prompt: str) -> BaseModel:
    ids = [item["arxiv_id"] for item in json.loads(prompt)]
    return PaperScoreBatch(scores=[make_score(arxiv_id) for arxiv_id in ids])


def test_scores_papers_in_batches() -> None:
    llm = FakeLLM({PaperScoreBatch: score_every_paper})
    papers = [make_paper(f"2610.0000{i}") for i in range(5)]
    result = PaperScorer(llm, batch_size=2).score(papers)
    assert len(llm.calls) == 3
    assert [r.paper.arxiv_id for r in result] == [p.arxiv_id for p in papers]
    assert "Score EVERY paper" in llm.calls[0][0]


def test_ignores_unknown_and_duplicate_ids() -> None:
    def answer(prompt: str) -> BaseModel:
        return PaperScoreBatch(
            scores=[make_score("2610.00001"), make_score("2610.00001"), make_score("9999.99999")]
        )

    result = PaperScorer(FakeLLM({PaperScoreBatch: answer}), batch_size=10).score(
        [make_paper("2610.00001"), make_paper("2610.00002")]
    )
    assert [r.paper.arxiv_id for r in result] == ["2610.00001"]


def test_skips_a_batch_with_invalid_output() -> None:
    calls = 0

    def flaky(prompt: str) -> BaseModel:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LLMOutputError("bad json")
        return score_every_paper(prompt)

    papers = [make_paper("2610.00001"), make_paper("2610.00002")]
    result = PaperScorer(FakeLLM({PaperScoreBatch: flaky}), batch_size=1).score(papers)
    assert [r.paper.arxiv_id for r in result] == ["2610.00002"]
