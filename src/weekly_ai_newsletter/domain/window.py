from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class TimeWindow:
    """Half-open time interval [start, end) with timezone-aware bounds."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeWindow bounds must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("TimeWindow start must be before end")

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    @classmethod
    def week_before(cls, run_date: date, *, lag_days: int = 0) -> TimeWindow:
        end = datetime.combine(run_date - timedelta(days=lag_days), time.min, tzinfo=UTC)
        return cls(start=end - timedelta(days=7), end=end)
