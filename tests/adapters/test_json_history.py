from datetime import date
from pathlib import Path

from weekly_ai_newsletter.adapters.json_history import JsonHistoryStore
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
