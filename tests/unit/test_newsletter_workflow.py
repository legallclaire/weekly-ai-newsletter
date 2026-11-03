import os
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from weekly_ai_newsletter.scheduling import is_send_time

WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "newsletter.yml"


def _workflow(path: Path = WORKFLOW) -> Any:
    return yaml.safe_load(path.read_text())


def _cron_times(day: date) -> list[datetime]:
    times = []
    # PyYAML reads the `on` key as the boolean True.
    for entry in _workflow()[True]["schedule"]:
        minute, hours, *_ = entry["cron"].split()
        for hour in hours.split(","):
            times.append(datetime(day.year, day.month, day.day, int(hour), int(minute), tzinfo=UTC))
    return times


@pytest.mark.parametrize("wednesday", [date(2026, 11, 4), date(2026, 7, 1)])
def test_a_trigger_lands_at_seven_paris_with_a_backup(wednesday: date) -> None:
    on_time = [t for t in _cron_times(wednesday) if is_send_time(t)]
    assert len(on_time) >= 2, "a late or dropped cron run must have a backup trigger"
    assert min(on_time).astimezone(on_time[0].tzinfo).minute < 15
    # The first trigger inside the window must be in the 07:xx Paris hour.
    assert not is_send_time(min(on_time) - timedelta(hours=1))


def _step(name: str, job: str = "send") -> str:
    [step] = [s for s in _workflow()["jobs"][job]["steps"] if s.get("name") == name]
    return str(step["run"])


def test_send_gate_fails_loudly_when_the_guard_crashes(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    fake_uv.write_text("#!/bin/sh\necho boom >&2\nexit 1\n")
    fake_uv.chmod(0o755)
    script = _step("Check send time (Europe/Paris)").replace("${{ github.event_name }}", "schedule")
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(tmp_path / "out"),
        },
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0


def test_history_commit_survives_a_moved_default_branch() -> None:
    script = _step("Commit archive and history", job="commit")
    assert "git pull --rebase" in script


def test_only_the_commit_job_can_write_to_the_repository() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    writers = [name for name, job in workflow["jobs"].items() if "permissions" in job]
    assert writers == ["commit"]
    assert not any("uv" in step.get("run", "") for step in workflow["jobs"]["commit"]["steps"])


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_actions_are_pinned_and_checkouts_drop_credentials(path: Path) -> None:
    for job in _workflow(path)["jobs"].values():
        for step in job["steps"]:
            if "uses" not in step:
                continue
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
            if step["uses"].startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False


def test_uv_run_does_not_reinstall_dev_dependencies() -> None:
    # `uv sync --no-dev` installs the runtime only; a syncing `uv run` would add dev deps back.
    assert _workflow()["jobs"]["send"]["env"]["UV_NO_SYNC"] == "1"


def test_manual_run_still_skips_an_issue_already_sent_today(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(f'#!/bin/sh\necho "$@" > {tmp_path}/args\necho false\n')
    fake_uv.chmod(0o755)
    script = _step("Check send time (Europe/Paris)").replace(
        "${{ github.event_name }}", "workflow_dispatch"
    )
    subprocess.run(
        ["bash", "-e", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(tmp_path / "out"),
        },
        check=True,
    )
    assert "should-send --any-time" in (tmp_path / "args").read_text()
    assert (tmp_path / "out").read_text() == "send=false\n"
