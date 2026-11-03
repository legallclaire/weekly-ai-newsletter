from pathlib import Path

import httpx
import pytest

from tests.factories import make_feed_item, make_paper, make_repo
from tests.fakes import (
    DEVTOOLS_FEED,
    NEWS_FEED,
    FakeFeedSource,
    FakePaperSource,
    FakeRepoSearchSource,
    FakeTrendingSource,
    InMemoryHistoryStore,
    happy_llm,
)
from weekly_ai_newsletter import cli
from weekly_ai_newsletter.config import AppConfig, Secrets
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.pipeline import Dependencies, NewsletterPipeline

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def fake_build_pipeline(
    config: AppConfig,
    secrets: Secrets,
    http: httpx.Client,
    *,
    trending: FakeTrendingSource | None = None,
) -> NewsletterPipeline:
    deps = Dependencies(
        papers=FakePaperSource([make_paper(title="Agent planning")]),
        feeds=FakeFeedSource(
            {NEWS_FEED: [make_feed_item()], DEVTOOLS_FEED: [make_feed_item("https://gh.example/v")]}
        ),
        trending=trending or FakeTrendingSource([make_repo()]),
        repo_search=FakeRepoSearchSource(),
        vulnerabilities=(),
        llm=happy_llm(),
        history=InMemoryHistoryStore(),
    )
    return NewsletterPipeline(config, deps)


def run_args(preview: Path) -> list[str]:
    return [
        "run",
        "--dry-run",
        "--date",
        "2026-11-04",
        "--config-dir",
        str(REPO_CONFIG),
        "--preview",
        str(preview),
    ]


def test_dry_run_writes_preview_without_email_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for name in ("RESEND_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAIL", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)
    preview = tmp_path / "preview.html"
    assert cli.main(run_args(preview)) == 0
    assert "Agent planning" in preview.read_text()


def test_missing_secrets_exit_with_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["run", "--dry-run", "--config-dir", str(REPO_CONFIG)]) == 2


def test_real_run_without_email_secrets_exits_with_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert cli.main(["run", "--config-dir", str(REPO_CONFIG)]) == 2


def test_should_send_prints_a_boolean(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["should-send", "--config-dir", str(REPO_CONFIG)]) == 0
    assert capsys.readouterr().out.strip() in {"true", "false"}


def test_github_summary_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)
    assert cli.main(run_args(tmp_path / "p.html")) == 0
    assert "| papers |" in summary.read_text()


def test_failed_send_still_writes_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    for name in ("ANTHROPIC_API_KEY", "RESEND_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAIL"):
        monkeypatch.setenv(name, "x@example.com")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)  # has no email delivery
    args = [a for a in run_args(tmp_path / "p.html") if a != "--dry-run"]
    assert cli.main(args) == 1
    assert "| papers |" in summary.read_text()


def test_annotations_escape_multiline_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken_trending(
        config: AppConfig, secrets: Secrets, http: httpx.Client
    ) -> NewsletterPipeline:
        failing = FakeTrendingSource(SourceError("line one\nline two 100%"))
        return fake_build_pipeline(config, secrets, http, trending=failing)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cli, "build_pipeline", broken_trending)
    assert cli.main(run_args(tmp_path / "p.html")) == 0
    out = capsys.readouterr().out
    assert (
        "::warning title=Section unavailable::repos: SourceError: line one%0Aline two 100%25" in out
    )
