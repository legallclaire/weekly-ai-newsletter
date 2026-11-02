"""Send-time guard: GitHub cron is UTC-only and may fire late, Paris time has DST."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def is_send_time(now: datetime, *, hour: int = 7) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(PARIS).hour == hour


def should_send(now: datetime, archive_dir: Path, *, hour: int = 7) -> bool:
    """True at the send hour in Paris, unless today's issue was already archived."""
    if not is_send_time(now, hour=hour):
        return False
    today = now.astimezone(PARIS).date()
    return not (archive_dir / f"{today.isoformat()}.html").exists()
