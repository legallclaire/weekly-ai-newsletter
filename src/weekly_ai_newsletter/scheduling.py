"""Send-time guard: GitHub cron is UTC-only and may fire late, Paris time has DST."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


# Scheduled runs can start an hour or more late; the archive check prevents double sends.
LATE_WINDOW_HOURS = 3


def is_send_time(now: datetime, *, hour: int = 7) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return hour <= now.astimezone(PARIS).hour < hour + LATE_WINDOW_HOURS


def should_send(now: datetime, archive_dir: Path, *, hour: int = 7, any_time: bool = False) -> bool:
    """True from the send hour in Paris until a few hours later, unless already archived.

    `any_time` (manual runs) skips the hour check but never the archive check.
    """
    if not any_time and not is_send_time(now, hour=hour):
        return False
    today = now.astimezone(PARIS).date()
    return not (archive_dir / f"{today.isoformat()}.html").exists()
