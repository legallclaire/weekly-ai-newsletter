from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from tests.factories import make_score
from weekly_ai_newsletter.config import (
    AppConfig,
    FeedConfig,
    Keywords,
    PaperKeywords,
    PaperSettings,
    RepoKeywords,
    Settings,
    Sources,
)
from weekly_ai_newsletter.domain.history import History
from weekly_ai_newsletter.domain.models import FeedItem, OutgoingEmail, Paper, Repo
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.services.devtools_curator import ChangePick, DevToolsSelection, ToolGroup
from weekly_ai_newsletter.services.news_curator import NewsPick, NewsSelection
from weekly_ai_newsletter.services.paper_scorer import PaperScoreBatch
from weekly_ai_newsletter.services.paper_writer import PaperWriteup, PaperWriteupBatch
from weekly_ai_newsletter.services.repo_curator import RepoVerdict, RepoVerdicts

Handler = Callable[[str], BaseModel] | BaseModel | Exception

NEWS_FEED = "https://lab.example/feed"
DEVTOOLS_FEED = "https://github.com/anthropics/claude-code/releases.atom"


class FakeLLM:
    """LLMClient double: answers by output model type, records every call."""

    def __init__(self, responses: Mapping[type[BaseModel], Handler]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        self.calls.append((system, prompt, output_model))
        handler = self._responses[output_model]
        if isinstance(handler, Exception):
            raise handler
        result = handler if isinstance(handler, BaseModel) else handler(prompt)
        assert isinstance(result, output_model)
        return result


class FakePaperSource:
    def __init__(self, papers: Sequence[Paper] | Exception = ()) -> None:
        self._papers = papers
        self.windows: list[TimeWindow] = []

    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]:
        self.windows.append(window)
        if isinstance(self._papers, Exception):
            raise self._papers
        return list(self._papers)


class FakeFeedSource:
    def __init__(self, items_by_url: Mapping[str, Sequence[FeedItem] | Exception]) -> None:
        self._items = items_by_url

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        items = self._items.get(url, [])
        if isinstance(items, Exception):
            raise items
        return list(items)


class FakeTrendingSource:
    def __init__(self, repos: Sequence[Repo] | Exception = ()) -> None:
        self._repos = repos

    def fetch_weekly(self) -> list[Repo]:
        if isinstance(self._repos, Exception):
            raise self._repos
        return list(self._repos)


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        self.sent.append(message)


class InMemoryHistoryStore:
    def __init__(self, history: History | None = None) -> None:
        self.history = history or History()
        self.saves = 0

    def load(self) -> History:
        return History(entries={kind: dict(b) for kind, b in self.history.entries.items()})

    def save(self, history: History) -> None:
        self.history = history
        self.saves += 1


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        settings=Settings(
            papers=PaperSettings(categories=["cs.AI"]),
            history_path=tmp_path / "state" / "history.json",
            archive_dir=tmp_path / "archive",
        ),
        sources=Sources(
            news=[FeedConfig(name="Lab", url=NEWS_FEED)],
            devtools=[FeedConfig(name="Claude Code", url=DEVTOOLS_FEED)],
        ),
        keywords=Keywords(
            papers=PaperKeywords(positive={"agent": 3}),
            repos=RepoKeywords(include=["llm", "agent"], exclude=["awesome"]),
        ),
    )


def happy_llm() -> FakeLLM:
    """An LLM that scores every paper highly and keeps every candidate."""

    def scores(prompt: str) -> BaseModel:
        ids = [p["arxiv_id"] for p in json.loads(prompt)]
        return PaperScoreBatch(scores=[make_score(i, relevance=9, novelty=8) for i in ids])

    def writeups(prompt: str) -> BaseModel:
        return PaperWriteupBatch(
            writeups=[
                PaperWriteup(arxiv_id=p["arxiv_id"], summary="Résumé.", why_selected="Utile.")
                for p in json.loads(prompt)
            ]
        )

    def news(prompt: str) -> BaseModel:
        return NewsSelection(
            picks=[NewsPick(index=p["index"], summary="Résumé.") for p in json.loads(prompt)]
        )

    def devtools(prompt: str) -> BaseModel:
        changes = [ChangePick(index=p["index"], summary="Nouveau.") for p in json.loads(prompt)]
        return DevToolsSelection(groups=[ToolGroup(tool="Claude Code", changes=changes)])

    def repos(prompt: str) -> BaseModel:
        return RepoVerdicts(
            verdicts=[
                RepoVerdict(full_name=r["full_name"], keep=True, why_interesting="Utile.")
                for r in json.loads(prompt)
            ]
        )

    return FakeLLM(
        {
            PaperScoreBatch: scores,
            PaperWriteupBatch: writeups,
            NewsSelection: news,
            DevToolsSelection: devtools,
            RepoVerdicts: repos,
        }
    )
