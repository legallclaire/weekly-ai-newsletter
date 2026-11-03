from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class HistoryKind(StrEnum):
    PAPER = "papers"
    NEWS = "news"
    DEVTOOL = "devtools"
    REPO = "repos"
    EXTENSION = "extensions"
    SECURITY = "security"


@dataclass
class History:
    """What was already sent, and when, keyed by kind then item key."""

    entries: dict[HistoryKind, dict[str, date]] = field(default_factory=dict)

    def was_sent(self, kind: HistoryKind, key: str, *, on_or_after: date | None = None) -> bool:
        sent_on = self.entries.get(kind, {}).get(key)
        if sent_on is None:
            return False
        return on_or_after is None or sent_on >= on_or_after

    def record(self, kind: HistoryKind, keys: Iterable[str], on: date) -> None:
        bucket = self.entries.setdefault(kind, {})
        for key in keys:
            bucket[key] = on
