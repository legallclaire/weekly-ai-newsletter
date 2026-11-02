from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tests.factories import make_feed_item, make_paper, make_repo
from tests.fakes import (
    DEVTOOLS_FEED,
    NEWS_FEED,
    FakeEmailSender,
    FakeFeedSource,
    FakePaperSource,
    FakeTrendingSource,
    InMemoryHistoryStore,
    happy_llm,
    make_config,
)
from weekly_ai_newsletter.domain.errors import PipelineError, SourceError
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.pipeline import Delivery, Dependencies, NewsletterPipeline

RUN_DATE = date(2026, 11, 4)


def build(
    tmp_path: Path,
    *,
    papers: FakePaperSource | None = None,
    feeds: FakeFeedSource | None = None,
    trending: FakeTrendingSource | None = None,
    history: InMemoryHistoryStore | None = None,
    email: FakeEmailSender | None = None,
) -> NewsletterPipeline:
    deps = Dependencies(
        papers=papers or FakePaperSource([make_paper("2610.00001", title="Agent planning")]),
        feeds=feeds
        or FakeFeedSource(
            {
                NEWS_FEED: [make_feed_item("https://lab.example/x", title="Model X")],
                DEVTOOLS_FEED: [make_feed_item("https://gh.example/v2", title="v2.1.0")],
            }
        ),
        trending=trending or FakeTrendingSource([make_repo("acme/agent-kit")]),
        llm=happy_llm(),
        history=history or InMemoryHistoryStore(),
    )
    delivery = Delivery(email, "from@x.dev", "to@x.dev") if email else None
    return NewsletterPipeline(make_config(tmp_path), deps, delivery=delivery)


def test_build_and_publish_happy_path(tmp_path: Path) -> None:
    email, history = FakeEmailSender(), InMemoryHistoryStore()
    pipeline = build(tmp_path, email=email, history=history)
    result = pipeline.build(RUN_DATE)
    pipeline.publish(result)

    [sent] = email.sent
    assert sent.subject == "Veille IA hebdo — 4 novembre 2026"
    assert sent.idempotency_key == "weekly-ai-newsletter-2026-11-04"
    for expected in ("Model X", "v2.1.0", "Agent planning", "acme/agent-kit"):
        assert expected in sent.html
    assert (tmp_path / "archive" / "2026-11-04.html").read_text() == sent.html
    saved = history.history
    assert saved.was_sent(HistoryKind.PAPER, "2610.00001")
    assert saved.was_sent(HistoryKind.NEWS, "https://lab.example/x")
    assert saved.was_sent(HistoryKind.DEVTOOL, "https://gh.example/v2")
    assert saved.was_sent(HistoryKind.REPO, "acme/agent-kit")
    assert "papers" in result.report.stages and not result.report.failures


def test_failing_section_degrades_without_sinking_the_newsletter(tmp_path: Path) -> None:
    pipeline = build(tmp_path, trending=FakeTrendingSource(SourceError("layout changed")))
    result = pipeline.build(RUN_DATE)
    assert not result.newsletter.repos.available
    assert result.newsletter.papers.available
    assert "layout changed" in result.report.failures["repos"]
    assert "Rubrique indisponible cette semaine." in result.rendered.html


def test_every_section_failing_is_fatal(tmp_path: Path) -> None:
    boom = SourceError("down")
    pipeline = build(
        tmp_path,
        papers=FakePaperSource(boom),
        feeds=FakeFeedSource({NEWS_FEED: boom, DEVTOOLS_FEED: boom}),
        trending=FakeTrendingSource(boom),
    )
    with pytest.raises(PipelineError):
        pipeline.build(RUN_DATE)


def test_quiet_week_is_not_a_failure(tmp_path: Path) -> None:
    pipeline = build(tmp_path, papers=FakePaperSource([]), feeds=FakeFeedSource({}))
    result = pipeline.build(RUN_DATE)
    assert result.newsletter.papers.available and result.newsletter.papers.items == ()
    assert result.newsletter.news.available and result.newsletter.news.items == ()
    assert "Rien d'assez solide cette semaine." in result.rendered.text


def test_one_broken_feed_is_a_warning_not_a_failure(tmp_path: Path) -> None:
    feeds = FakeFeedSource(
        {NEWS_FEED: SourceError("404"), DEVTOOLS_FEED: [make_feed_item("https://gh.example/v2")]}
    )
    result = build(tmp_path, feeds=feeds).build(RUN_DATE)
    assert not result.newsletter.news.available  # its only feed failed
    assert result.newsletter.devtools.available
    assert any("Lab" in warning for warning in result.report.warnings)


def test_already_sent_items_are_not_resent(tmp_path: Path) -> None:
    previous = History()
    previous.record(HistoryKind.NEWS, ["https://lab.example/x"], date(2026, 10, 28))
    result = build(tmp_path, history=InMemoryHistoryStore(previous)).build(RUN_DATE)
    assert result.newsletter.news.items == ()


def test_paper_window_is_lagged_by_two_days(tmp_path: Path) -> None:
    papers = FakePaperSource([])
    build(tmp_path, papers=papers).build(RUN_DATE)
    [window] = papers.windows
    assert window.end == datetime(2026, 11, 2, tzinfo=UTC)


def test_publish_requires_delivery(tmp_path: Path) -> None:
    pipeline = build(tmp_path)
    with pytest.raises(PipelineError, match="delivery"):
        pipeline.publish(pipeline.build(RUN_DATE))


def test_report_markdown_lists_funnels_and_failures(tmp_path: Path) -> None:
    pipeline = build(tmp_path, trending=FakeTrendingSource(SourceError("layout changed")))
    markdown = pipeline.build(RUN_DATE).report.to_markdown()
    assert "| papers |" in markdown
    assert "**repos**" in markdown
