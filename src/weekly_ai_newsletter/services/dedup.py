from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from weekly_ai_newsletter.domain.history import History, HistoryKind


def unique_by[T](items: Iterable[T], key: Callable[[T], str]) -> list[T]:
    seen: set[str] = set()
    unique: list[T] = []
    for item in items:
        if key(item) not in seen:
            seen.add(key(item))
            unique.append(item)
    return unique


def drop_sent[T](
    items: Iterable[T],
    *,
    key: Callable[[T], str],
    history: History,
    kind: HistoryKind,
    since: date | None = None,
) -> list[T]:
    """Remove items already sent (only those sent on/after `since`, when given)."""
    return [item for item in items if not history.was_sent(kind, key(item), on_or_after=since)]
