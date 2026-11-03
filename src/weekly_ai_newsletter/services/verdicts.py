from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol


class KeepVerdict(Protocol):
    @property
    def full_name(self) -> str: ...
    @property
    def keep(self) -> bool: ...
    @property
    def why_interesting(self) -> str: ...


def kept_by_verdict[T](
    candidates: Sequence[T], verdicts: Iterable[KeepVerdict], *, name: Callable[[T], str]
) -> list[tuple[T, str]]:
    """Candidates the LLM chose to keep, with its reason.

    Verdicts for names that were not candidates (invented by the model) or already judged
    (repeated) are ignored.
    """
    pending = {name(candidate): candidate for candidate in candidates}
    kept: list[tuple[T, str]] = []
    for verdict in verdicts:
        candidate = pending.pop(verdict.full_name, None)
        if candidate is not None and verdict.keep:
            kept.append((candidate, verdict.why_interesting))
    return kept
