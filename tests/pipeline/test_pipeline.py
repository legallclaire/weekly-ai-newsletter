import threading
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from tests.factories import make_extension, make_feed_item, make_paper, make_repo
from tests.fakes import (
    DEVTOOLS_FEED,
    NEWS_FEED,
    FakeEmailSender,
    FakeFeedSource,
    FakePaperSource,
    FakeRepoSearchSource,
    FakeTrendingSource,
    InMemoryHistoryStore,
    happy_llm,
    make_config,
)
from weekly_ai_newsletter.config import FeedConfig
from weekly_ai_newsletter.domain.errors import PipelineError, SourceError
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.pipeline import Delivery, Dependencies, NewsletterPipeline

RUN_DATE = date(2026, 11, 4)


def build(
    tmp_path: Path,
    *,
    papers: FakePaperSource | None = None,
    feeds: FakeFeedSource | None = None,
    trending: FakeTrendingSource | None = None,
    extensions: FakeRepoSearchSource | None = None,
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
        repo_search=extensions or FakeRepoSearchSource([make_extension("acme/review-skill")]),
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
    for expected in ("Model X", "v2.1.0", "Agent planning", "acme/agent-kit", "acme/review-skill"):
        assert expected in sent.html
    assert (tmp_path / "archive" / "2026-11-04.html").read_text() == sent.html
    saved = history.history
    assert saved.was_sent(HistoryKind.PAPER, "2610.00001")
    assert saved.was_sent(HistoryKind.NEWS, "https://lab.example/x")
    assert saved.was_sent(HistoryKind.DEVTOOL, "https://gh.example/v2")
    assert saved.was_sent(HistoryKind.REPO, "acme/agent-kit")
    assert saved.was_sent(HistoryKind.EXTENSION, "acme/review-skill")
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
        extensions=FakeRepoSearchSource(boom),
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


def test_extensions_skip_this_weeks_trending_repos_and_past_issues(tmp_path: Path) -> None:
    previous = History()
    previous.record(HistoryKind.EXTENSION, ["old/skill"], date(2026, 9, 2))
    search = FakeRepoSearchSource(
        [make_extension("acme/agent-kit"), make_extension("old/skill"), make_extension("new/skill")]
    )
    result = build(tmp_path, extensions=search, history=InMemoryHistoryStore(previous)).build(
        RUN_DATE
    )
    assert [e.repo.full_name for e in result.newsletter.extensions.items] == ["new/skill"]
    [(topics, created_after, min_stars)] = search.queries
    assert created_after == date(2026, 10, 5) and min_stars == 50 and "mcp-server" in topics


def test_failing_extension_search_degrades_its_section_only(tmp_path: Path) -> None:
    result = build(tmp_path, extensions=FakeRepoSearchSource(SourceError("rate limited"))).build(
        RUN_DATE
    )
    assert not result.newsletter.extensions.available
    assert result.newsletter.repos.available
    assert "rate limited" in result.report.failures["extensions"]


def test_report_keeps_raw_third_party_errors_out_of_the_public_summary(tmp_path: Path) -> None:
    request = httpx.Request("GET", "https://feeds.example/rss?key=s3cret")
    forbidden = httpx.HTTPStatusError(
        "403 for https://feeds.example/rss?key=s3cret",
        request=request,
        response=httpx.Response(403, request=request),
    )
    result = build(
        tmp_path,
        feeds=FakeFeedSource({NEWS_FEED: forbidden, DEVTOOLS_FEED: []}),
        trending=FakeTrendingSource(RuntimeError("internal detail s3cret")),
    ).build(RUN_DATE)
    assert result.report.warnings == ["feed Lab failed: HTTP 403 from feeds.example"]
    assert result.report.failures["repos"] == "RuntimeError"
    assert "s3cret" not in result.report.to_markdown()


def test_publish_refuses_an_issue_already_archived(tmp_path: Path) -> None:
    email = FakeEmailSender()
    pipeline = build(tmp_path, email=email)
    result = pipeline.build(RUN_DATE)
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "2026-11-04.html").write_text("already sent")
    with pytest.raises(PipelineError, match="already"):
        pipeline.publish(result)
    assert email.sent == []


class BrokenHistoryStore(InMemoryHistoryStore):
    def save(self, history: History) -> None:
        raise OSError("disk full")


def test_failure_after_sending_says_the_email_went_out(tmp_path: Path) -> None:
    email = FakeEmailSender()
    pipeline = build(tmp_path, email=email, history=BrokenHistoryStore())
    with pytest.raises(PipelineError, match="sent"):
        pipeline.publish(pipeline.build(RUN_DATE))
    assert len(email.sent) == 1


class RendezvousFeedSource:
    """News feeds only answer once all of them are being fetched at the same time."""

    def __init__(self, urls: set[str]) -> None:
        self._urls = urls
        self._barrier = threading.Barrier(len(urls), timeout=2)

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        if url not in self._urls:
            return []
        self._barrier.wait()
        return [make_feed_item(f"{url}/post", title=f"Post from {name}")]


def test_feeds_of_a_section_are_fetched_concurrently(tmp_path: Path) -> None:
    feeds = [FeedConfig(name=f"Lab {n}", url=f"https://lab{n}.example/feed") for n in range(3)]
    base = make_config(tmp_path)
    config = replace(base, sources=base.sources.model_copy(update={"news": feeds}))
    deps = Dependencies(
        papers=FakePaperSource([]),
        feeds=RendezvousFeedSource({feed.url for feed in feeds}),
        trending=FakeTrendingSource([]),
        repo_search=FakeRepoSearchSource(),
        llm=happy_llm(),
        history=InMemoryHistoryStore(),
    )
    result = NewsletterPipeline(config, deps).build(RUN_DATE)
    assert result.newsletter.news.available
    assert len(result.newsletter.news.items) == 3
    assert not result.report.warnings
