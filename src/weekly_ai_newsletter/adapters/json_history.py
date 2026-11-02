from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from weekly_ai_newsletter.domain.history import History, HistoryKind


class JsonHistoryStore:
    """History persisted as a sorted, diff-friendly JSON file committed to the repo."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> History:
        if not self._path.exists():
            return History()
        raw: dict[str, dict[str, str]] = json.loads(self._path.read_text(encoding="utf-8"))
        return History(
            entries={
                HistoryKind(kind): {key: date.fromisoformat(day) for key, day in bucket.items()}
                for kind, bucket in raw.items()
            }
        )

    def save(self, history: History) -> None:
        data = {
            kind.value: {key: day.isoformat() for key, day in sorted(bucket.items())}
            for kind, bucket in sorted(history.entries.items())
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
