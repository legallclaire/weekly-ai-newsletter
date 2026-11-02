from datetime import UTC, datetime
from pathlib import Path

import pytest

from weekly_ai_newsletter.scheduling import is_send_time, should_send


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 11, 4, 6, 10, tzinfo=UTC), True),  # winter: 07:10 Paris
        (datetime(2026, 11, 4, 5, 10, tzinfo=UTC), False),  # winter: 06:10 Paris
        (datetime(2026, 7, 1, 5, 25, tzinfo=UTC), True),  # summer: 07:25 Paris
        (datetime(2026, 7, 1, 6, 5, tzinfo=UTC), False),  # summer: 08:05 Paris
    ],
)
def test_send_time_follows_paris_daylight_saving(utc: datetime, expected: bool) -> None:
    assert is_send_time(utc) is expected


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        is_send_time(datetime(2026, 11, 4, 6))


def test_second_trigger_on_the_same_day_does_not_send(tmp_path: Path) -> None:
    now = datetime(2026, 11, 4, 6, 40, tzinfo=UTC)
    assert should_send(now, tmp_path)
    (tmp_path / "2026-11-04.html").write_text("sent")
    assert not should_send(now, tmp_path)
