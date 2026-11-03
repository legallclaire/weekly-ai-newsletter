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
        (datetime(2026, 7, 1, 6, 5, tzinfo=UTC), True),  # summer: 08:05 Paris, late cron
        (datetime(2026, 7, 1, 7, 59, tzinfo=UTC), True),  # summer: 09:59 Paris, very late cron
        (datetime(2026, 7, 1, 8, 0, tzinfo=UTC), False),  # summer: 10:00 Paris, too late
        (datetime(2026, 7, 1, 4, 59, tzinfo=UTC), False),  # summer: 06:59 Paris, too early
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


def test_any_time_ignores_the_hour_but_not_the_archive(tmp_path: Path) -> None:
    afternoon = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)
    assert not should_send(afternoon, tmp_path)
    assert should_send(afternoon, tmp_path, any_time=True)
    (tmp_path / "2026-11-04.html").write_text("sent")
    assert not should_send(afternoon, tmp_path, any_time=True)
