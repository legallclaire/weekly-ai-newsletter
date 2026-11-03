import os
from datetime import date
from pathlib import Path

import pytest

from weekly_ai_newsletter.adapters.json_history import JsonHistoryStore
from weekly_ai_newsletter.domain.errors import StateError
from weekly_ai_newsletter.domain.history import History, HistoryKind


def test_missing_file_loads_empty_history(tmp_path: Path) -> None:
    assert JsonHistoryStore(tmp_path / "nope.json").load().entries == {}


def test_round_trip_is_stable_and_human_readable(tmp_path: Path) -> None:
    path = tmp_path / "state" / "history.json"
    history = History()
    history.record(HistoryKind.PAPER, ["2610.00002", "2610.00001"], date(2026, 11, 4))
    store = JsonHistoryStore(path)
    store.save(history)
    assert store.load() == history
    text = path.read_text(encoding="utf-8")
    assert text.index("2610.00001") < text.index("2610.00002")
    assert '"2026-11-04"' in text


def test_interrupted_save_keeps_the_previous_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "history.json"
    store = JsonHistoryStore(path)
    first = History()
    first.record(HistoryKind.PAPER, ["2610.00001"], date(2026, 10, 28))
    store.save(first)
    before = path.read_text()

    def crash(*args: object) -> None:
        raise OSError("killed mid-write")

    monkeypatch.setattr(os, "replace", crash)
    second = History()
    second.record(HistoryKind.PAPER, ["2610.00002"], date(2026, 11, 4))
    with pytest.raises(OSError):
        store.save(second)
    assert path.read_text() == before
    assert [p.name for p in tmp_path.iterdir()] == ["history.json"]


def test_corrupt_history_is_a_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text('{"paper": {"2610.0')
    with pytest.raises(StateError, match=r"history\.json"):
        JsonHistoryStore(path).load()
