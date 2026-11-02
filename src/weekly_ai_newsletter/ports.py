"""Interfaces between the core logic and the outside world."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from weekly_ai_newsletter.domain.history import History
from weekly_ai_newsletter.domain.models import FeedItem, OutgoingEmail, Paper, Repo
from weekly_ai_newsletter.domain.window import TimeWindow


class PaperSource(Protocol):
    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]: ...


class FeedSource(Protocol):
    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]: ...


class TrendingSource(Protocol):
    def fetch_weekly(self) -> list[Repo]: ...


class LLMClient(Protocol):
    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        """Return the model's answer parsed and validated as `output_model`.

        Raises LLMOutputError when no valid output could be obtained.
        """
        ...


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


class HistoryStore(Protocol):
    def load(self) -> History: ...

    def save(self, history: History) -> None: ...
