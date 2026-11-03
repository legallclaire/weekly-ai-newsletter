from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from weekly_ai_newsletter.domain.models import (
    CuratedExtension,
    CuratedRepo,
    DevToolGroup,
    NewsItem,
    SecurityAlert,
    SelectedPaper,
)


@dataclass(frozen=True)
class Section[T]:
    """Items of one newsletter section, or the reason it is unavailable."""

    items: tuple[T, ...] = ()
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.error is None

    @classmethod
    def ok(cls, items: Iterable[T]) -> Section[T]:
        return cls(items=tuple(items))

    @classmethod
    def unavailable(cls, error: str) -> Section[T]:
        return cls(error=error)


@dataclass(frozen=True)
class Newsletter:
    issue_date: date
    language: str
    news: Section[NewsItem]
    devtools: Section[DevToolGroup]
    papers: Section[SelectedPaper]
    repos: Section[CuratedRepo]
    extensions: Section[CuratedExtension]
    security: Section[SecurityAlert]

    @property
    def sections(self) -> dict[str, Section[Any]]:
        return {
            "news": self.news,
            "devtools": self.devtools,
            "papers": self.papers,
            "repos": self.repos,
            "extensions": self.extensions,
            "security": self.security,
        }

    @property
    def all_unavailable(self) -> bool:
        return not any(section.available for section in self.sections.values())
