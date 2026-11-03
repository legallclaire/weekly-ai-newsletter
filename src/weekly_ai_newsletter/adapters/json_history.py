from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from weekly_ai_newsletter.domain.errors import StateError
from weekly_ai_newsletter.domain.history import History, HistoryKind


class JsonHistoryStore:
    """History persisted as a sorted, diff-friendly JSON file committed to the repo."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> History:
        if not self._path.exists():
            return History()
        try:
            raw: dict[str, dict[str, str]] = json.loads(self._path.read_text(encoding="utf-8"))
            return History(
                entries={
                    HistoryKind(kind): {key: date.fromisoformat(day) for key, day in bucket.items()}
                    for kind, bucket in raw.items()
                }
            )
        except (ValueError, AttributeError) as exc:  # JSONDecodeError is a ValueError
            raise StateError(f"{self._path} is not a valid history file: {exc}") from exc

    def save(self, history: History) -> None:
        data = {
            kind.value: {key: day.isoformat() for key, day in sorted(bucket.items())}
            for kind, bucket in sorted(history.entries.items())
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write a sibling file then rename it over the old one, so a crash never leaves a
        # truncated history behind.
        temporary = self._path.with_name(f".{self._path.name}.tmp")
        try:
            temporary.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)
