import pytest

from tests.factories import make_paper, make_score
from tests.fakes import FakeLLM
from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import ScoredPaper
from weekly_ai_newsletter.services.paper_writer import (
    PaperWriter,
    PaperWriteup,
    PaperWriteupBatch,
)

SELECTED = [ScoredPaper(make_paper("2610.00001", title="Agents"), make_score("2610.00001"))]


def test_writes_summary_and_reason_in_configured_language() -> None:
    llm = FakeLLM(
        {
            PaperWriteupBatch: PaperWriteupBatch(
                writeups=[
                    PaperWriteup(arxiv_id="2610.00001", summary="Résumé.", why_selected="Car.")
                ]
            )
        }
    )
    [paper] = PaperWriter(llm, language="fr").write(SELECTED)
    assert (paper.summary, paper.why_selected) == ("Résumé.", "Car.")
    assert paper.paper.title == "Agents"
    assert "French" in llm.calls[0][0]


def test_missing_writeup_is_an_error() -> None:
    llm = FakeLLM({PaperWriteupBatch: PaperWriteupBatch(writeups=[])})
    with pytest.raises(LLMOutputError, match=r"2610\.00001"):
        PaperWriter(llm, language="en").write(SELECTED)


def test_no_call_when_nothing_selected() -> None:
    llm = FakeLLM({})
    assert PaperWriter(llm, language="en").write([]) == []
    assert llm.calls == []
