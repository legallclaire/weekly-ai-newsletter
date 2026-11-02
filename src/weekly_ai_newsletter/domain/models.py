from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_TOTAL = 70


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: tuple[str, ...]
    url: str
    published: datetime
    categories: tuple[str, ...]


class PaperScore(BaseModel):
    """Per-criterion scores produced by the LLM; the total is computed here."""

    model_config = ConfigDict(frozen=True)

    arxiv_id: str
    relevance: int = Field(ge=1, le=10)
    novelty: int = Field(ge=1, le=10)
    evidence: int = Field(ge=1, le=10)
    depth: int = Field(ge=1, le=10)
    practical_utility: int = Field(ge=1, le=10)
    is_incremental: bool
    rationale: str

    @property
    def total(self) -> int:
        return (
            2 * self.relevance
            + 2 * self.novelty
            + self.evidence
            + self.depth
            + self.practical_utility
        )


@dataclass(frozen=True)
class ScoredPaper:
    paper: Paper
    score: PaperScore


@dataclass(frozen=True)
class SelectedPaper:
    paper: Paper
    score: PaperScore
    summary: str
    why_selected: str
    enterprise_use: str = ""


@dataclass(frozen=True)
class FeedItem:
    title: str
    url: str
    summary: str
    published: datetime
    source: str


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    summary: str


@dataclass(frozen=True)
class DevToolChange:
    title: str
    url: str
    summary: str


@dataclass(frozen=True)
class DevToolGroup:
    tool: str
    changes: tuple[DevToolChange, ...]


@dataclass(frozen=True)
class Repo:
    full_name: str
    url: str
    description: str
    language: str | None
    stars: int
    stars_this_week: int


@dataclass(frozen=True)
class CuratedRepo:
    repo: Repo
    why_interesting: str


@dataclass(frozen=True)
class OutgoingEmail:
    sender: str
    recipient: str
    subject: str
    html: str
    text: str
    idempotency_key: str
