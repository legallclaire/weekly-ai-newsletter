"""Orchestration: build independent sections, render, then publish."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta

from weekly_ai_newsletter.config import AppConfig, FeedConfig
from weekly_ai_newsletter.domain.errors import (
    LLMOutputError,
    PipelineError,
    SourceError,
    describe_error,
)
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.domain.models import (
    CuratedExtension,
    CuratedRepo,
    DevToolGroup,
    FeedItem,
    NewsItem,
    OutgoingEmail,
    SelectedPaper,
)
from weekly_ai_newsletter.domain.newsletter import Newsletter, Section
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.ports import (
    EmailSender,
    FeedSource,
    HistoryStore,
    LLMClient,
    PaperSource,
    RepoSearchSource,
    TrendingSource,
)
from weekly_ai_newsletter.rendering.renderer import NewsletterRenderer, RenderedNewsletter
from weekly_ai_newsletter.services.dedup import drop_sent, unique_by
from weekly_ai_newsletter.services.devtools_curator import DevToolsCurator
from weekly_ai_newsletter.services.extension_curator import ExtensionCurator
from weekly_ai_newsletter.services.keyword_filter import KeywordFilter
from weekly_ai_newsletter.services.news_curator import NewsCurator
from weekly_ai_newsletter.services.paper_scorer import PaperScorer
from weekly_ai_newsletter.services.paper_selection import SelectionRules, select_papers
from weekly_ai_newsletter.services.paper_writer import PaperWriter
from weekly_ai_newsletter.services.repo_curator import RepoCurator
from weekly_ai_newsletter.services.repo_filter import RepoRuleFilter

logger = logging.getLogger(__name__)

FEED_WORKERS = 8


@dataclass(frozen=True)
class Dependencies:
    papers: PaperSource
    feeds: FeedSource
    trending: TrendingSource
    repo_search: RepoSearchSource
    llm: LLMClient
    history: HistoryStore


@dataclass(frozen=True)
class Delivery:
    sender: EmailSender
    from_address: str
    to_address: str


@dataclass
class RunReport:
    issue_date: date
    stages: dict[str, str] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"## Newsletter {self.issue_date.isoformat()}",
            "",
            "| Section | Funnel |",
            "|---|---|",
        ]
        lines += [f"| {name} | {funnel} |" for name, funnel in self.stages.items()]
        if self.failures:
            lines += ["", "### Unavailable sections", ""]
            lines += [f"- **{name}**: {error}" for name, error in self.failures.items()]
        if self.warnings:
            lines += ["", "### Warnings", ""]
            lines += [f"- {warning}" for warning in self.warnings]
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class BuildResult:
    newsletter: Newsletter
    rendered: RenderedNewsletter
    report: RunReport


class NewsletterPipeline:
    def __init__(
        self,
        config: AppConfig,
        deps: Dependencies,
        *,
        delivery: Delivery | None = None,
        renderer: NewsletterRenderer | None = None,
    ) -> None:
        settings = config.settings
        self._config = config
        self._deps = deps
        self._delivery = delivery
        self._renderer = renderer or NewsletterRenderer()
        self._keyword_filter = KeywordFilter(config.keywords.papers)
        self._repo_filter = RepoRuleFilter(config.keywords.repos)
        self._scorer = PaperScorer(deps.llm, batch_size=settings.papers.batch_size)
        self._writer = PaperWriter(deps.llm, language=settings.language)
        self._news_curator = NewsCurator(
            deps.llm, language=settings.language, max_items=settings.news.max_items
        )
        self._devtools_curator = DevToolsCurator(
            deps.llm,
            language=settings.language,
            secondary_tools=settings.devtools.secondary_tools,
        )
        self._repo_curator = RepoCurator(
            deps.llm, language=settings.language, max_items=settings.repos.max_items
        )
        self._extension_curator = ExtensionCurator(
            deps.llm,
            language=settings.language,
            max_items=settings.extensions.max_items,
            max_mcp=settings.extensions.max_mcp,
            mcp_topics=settings.extensions.mcp_topics,
        )
        self._rules = SelectionRules(
            min_total=settings.papers.min_total,
            min_novelty=settings.papers.min_novelty,
            max_selected=settings.papers.max_selected,
        )

    def build(self, run_date: date) -> BuildResult:
        history = self._deps.history.load()
        report = RunReport(issue_date=run_date)
        window = TimeWindow.week_before(run_date)
        repos = self._section("repos", report, lambda: self._repos(run_date, history, report))
        trending_names = {item.repo.full_name for item in repos.items}
        newsletter = Newsletter(
            issue_date=run_date,
            language=self._config.settings.language,
            news=self._section("news", report, lambda: self._news(window, history, report)),
            devtools=self._section(
                "devtools", report, lambda: self._devtools(window, history, report)
            ),
            papers=self._section("papers", report, lambda: self._papers(run_date, history, report)),
            repos=repos,
            extensions=self._section(
                "extensions",
                report,
                lambda: self._extensions(run_date, history, trending_names, report),
            ),
        )
        if newsletter.all_unavailable:
            raise PipelineError("every section failed; refusing to send an empty newsletter")
        return BuildResult(newsletter, self._renderer.render(newsletter), report)

    def publish(self, result: BuildResult) -> None:
        if self._delivery is None:
            raise PipelineError("email delivery is not configured")
        newsletter = result.newsletter
        archive_dir = self._config.settings.archive_dir
        archive_path = archive_dir / f"{newsletter.issue_date.isoformat()}.html"
        if archive_path.exists():
            raise PipelineError(f"the {newsletter.issue_date} issue was already sent")
        self._delivery.sender.send(
            OutgoingEmail(
                sender=self._delivery.from_address,
                recipient=self._delivery.to_address,
                subject=result.rendered.subject,
                html=result.rendered.html,
                text=result.rendered.text,
                idempotency_key=f"weekly-ai-newsletter-{newsletter.issue_date.isoformat()}",
            )
        )
        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(result.rendered.html, encoding="utf-8")
            history = self._deps.history.load()
            _record_sent(history, newsletter)
            self._deps.history.save(history)
        except OSError as exc:
            raise PipelineError(
                f"the email was sent but the archive or history could not be saved: {exc}"
            ) from exc

    def _section[T](self, name: str, report: RunReport, build: Callable[[], list[T]]) -> Section[T]:
        try:
            return Section.ok(build())
        except Exception as exc:  # a broken section must never sink the whole newsletter
            logger.exception("Section %s failed", name)
            report.failures[name] = describe_error(exc)
            return Section.unavailable(describe_error(exc))

    def _collect_feeds(
        self, feeds: Sequence[FeedConfig], window: TimeWindow, report: RunReport
    ) -> list[FeedItem]:
        def fetch(feed: FeedConfig) -> list[FeedItem] | Exception:
            try:
                return self._deps.feeds.fetch(feed.name, feed.url, window)
            except Exception as exc:  # one broken feed must not hide the others
                return exc

        # Feeds are independent network calls: fetch them together, report them in order.
        with ThreadPoolExecutor(max_workers=FEED_WORKERS) as pool:
            results = list(pool.map(fetch, feeds))
        items: list[FeedItem] = []
        failed = 0
        for feed, result in zip(feeds, results, strict=True):
            if isinstance(result, Exception):
                failed += 1
                logger.warning("Feed %s (%s) failed: %s", feed.name, feed.url, result)
                report.warnings.append(f"feed {feed.name} failed: {describe_error(result)}")
            else:
                items.extend(result)
        if feeds and failed == len(feeds):
            raise SourceError("every feed of this section failed")
        return items

    def _feed_candidates(
        self,
        feeds: Sequence[FeedConfig],
        *,
        kind: HistoryKind,
        max_candidates: int,
        window: TimeWindow,
        history: History,
        report: RunReport,
    ) -> tuple[int, list[FeedItem]]:
        """Fetched count, and the newest not-yet-sent items (one per URL)."""
        fetched = self._collect_feeds(feeds, window, report)
        fresh = drop_sent(
            unique_by(fetched, key=lambda i: i.url), key=lambda i: i.url, history=history, kind=kind
        )
        fresh.sort(key=lambda i: i.published, reverse=True)
        return len(fetched), fresh[:max_candidates]

    def _news(self, window: TimeWindow, history: History, report: RunReport) -> list[NewsItem]:
        fetched, candidates = self._feed_candidates(
            self._config.sources.news,
            kind=HistoryKind.NEWS,
            max_candidates=self._config.settings.news.max_candidates,
            window=window,
            history=history,
            report=report,
        )
        curated = self._news_curator.curate(candidates)
        report.stages["news"] = (
            f"{fetched} fetched -> {len(candidates)} candidates -> {len(curated)} selected"
        )
        return curated

    def _devtools(
        self, window: TimeWindow, history: History, report: RunReport
    ) -> list[DevToolGroup]:
        fetched, candidates = self._feed_candidates(
            self._config.sources.devtools,
            kind=HistoryKind.DEVTOOL,
            max_candidates=self._config.settings.devtools.max_candidates,
            window=window,
            history=history,
            report=report,
        )
        groups = self._devtools_curator.curate(candidates)
        changes = sum(len(group.changes) for group in groups)
        report.stages["devtools"] = (
            f"{fetched} fetched -> {len(candidates)} candidates -> "
            f"{changes} changes in {len(groups)} tools"
        )
        return groups

    def _papers(self, run_date: date, history: History, report: RunReport) -> list[SelectedPaper]:
        settings = self._config.settings.papers
        window = TimeWindow.week_before(run_date, lag_days=settings.window_lag_days)
        fetched = self._deps.papers.fetch(settings.categories, window)
        fresh = drop_sent(
            fetched, key=lambda p: p.arxiv_id, history=history, kind=HistoryKind.PAPER
        )
        shortlisted = self._keyword_filter.top(fresh, settings.prefilter_size)
        scored = self._scorer.score(shortlisted)
        if shortlisted and not scored:
            raise LLMOutputError("no paper could be scored")
        written = self._writer.write(select_papers(scored, self._rules))
        report.stages["papers"] = (
            f"{len(fetched)} fetched -> {len(shortlisted)} shortlisted -> "
            f"{len(scored)} scored -> {len(written)} selected"
        )
        return written

    def _repos(self, run_date: date, history: History, report: RunReport) -> list[CuratedRepo]:
        settings = self._config.settings.repos
        fetched = self._deps.trending.fetch_weekly()
        relevant = self._repo_filter.apply(fetched)
        fresh = drop_sent(
            relevant,
            key=lambda r: r.full_name,
            history=history,
            kind=HistoryKind.REPO,
            since=run_date - timedelta(weeks=settings.repeat_after_weeks),
        )
        curated = self._repo_curator.curate(fresh)
        report.stages["repos"] = (
            f"{len(fetched)} trending -> {len(fresh)} relevant -> {len(curated)} selected"
        )
        return curated

    def _extensions(
        self, run_date: date, history: History, exclude: set[str], report: RunReport
    ) -> list[CuratedExtension]:
        settings = self._config.settings.extensions
        fetched = self._deps.repo_search.search(
            settings.topics,
            created_after=run_date - timedelta(days=settings.created_within_days),
            min_stars=settings.min_stars,
        )
        fresh = drop_sent(
            (repo for repo in fetched if repo.full_name not in exclude),
            key=lambda r: r.full_name,
            history=history,
            kind=HistoryKind.EXTENSION,
        )
        candidates = fresh[: settings.max_candidates]
        curated = self._extension_curator.curate(candidates)
        report.stages["extensions"] = (
            f"{len(fetched)} found -> {len(candidates)} candidates -> {len(curated)} selected"
        )
        return curated


def _record_sent(history: History, newsletter: Newsletter) -> None:
    on = newsletter.issue_date
    history.record(HistoryKind.NEWS, (item.url for item in newsletter.news.items), on)
    history.record(
        HistoryKind.DEVTOOL,
        (change.url for group in newsletter.devtools.items for change in group.changes),
        on,
    )
    history.record(HistoryKind.PAPER, (p.paper.arxiv_id for p in newsletter.papers.items), on)
    history.record(HistoryKind.REPO, (r.repo.full_name for r in newsletter.repos.items), on)
    history.record(
        HistoryKind.EXTENSION, (e.repo.full_name for e in newsletter.extensions.items), on
    )
