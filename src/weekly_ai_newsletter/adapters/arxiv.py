from __future__ import annotations

import calendar
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.models import Paper
from weekly_ai_newsletter.domain.window import TimeWindow

ARXIV_API_URL = "https://export.arxiv.org/api/query"
_VERSION_SUFFIX = re.compile(r"v\d+$")


class ArxivPaperSource:
    """Papers submitted in a time window, via the arXiv Atom API (paginated, rate-limited)."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        page_size: int = 1000,
        max_results: int = 20000,
        delay_seconds: float = 3.0,
        short_page_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._page_size = page_size
        self._max_results = max_results
        self._delay = delay_seconds
        self._short_page_retries = short_page_retries
        self._sleep = sleep

    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]:
        query = (
            "(" + " OR ".join(f"cat:{category}" for category in categories) + ")"
            f" AND submittedDate:[{_arxiv_time(window.start)} TO {_arxiv_time(window.end)}]"
        )
        papers: dict[str, Paper] = {}
        for start in range(0, self._max_results, self._page_size):
            if start:
                self._sleep(self._delay)  # arXiv asks for >= 3 s between requests
            entries = self._fetch_page(query, start)
            for entry in entries:
                paper = _to_paper(entry)
                if window.contains(paper.published):
                    papers.setdefault(paper.arxiv_id, paper)
            if len(entries) < self._page_size:
                break
        return list(papers.values())

    def _fetch_page(self, query: str, start: int) -> list[Any]:
        """One page; arXiv sometimes answers 200 with a truncated page, which is retried."""
        for attempt in range(self._short_page_retries + 1):
            if attempt:
                self._sleep(self._delay)
            response = get_with_retry(
                self._client,
                ARXIV_API_URL,
                params={
                    "search_query": query,
                    "start": start,
                    "max_results": self._page_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                },
                sleep=self._sleep,
            )
            parsed = feedparser.parse(response.text)
            entries: list[Any] = list(parsed.entries)
            total = _total_results(parsed)
            expected = min(self._page_size, max(total - start, 0)) if total is not None else 0
            if len(entries) >= expected:
                return entries
        raise SourceError(
            f"arXiv returned {len(entries)} of {total} results at offset {start} after retries"
        )


def _total_results(parsed: Any) -> int | None:
    raw = parsed.feed.get("opensearch_totalresults")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _arxiv_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M")


def _clean(text: str) -> str:
    return " ".join(text.split())


def _to_paper(entry: Any) -> Paper:
    arxiv_id = _VERSION_SUFFIX.sub("", entry.id.rsplit("/abs/", 1)[-1])
    return Paper(
        arxiv_id=arxiv_id,
        title=_clean(entry.title),
        abstract=_clean(entry.summary),
        authors=tuple(author.get("name", "") for author in entry.get("authors", [])),
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published=datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=UTC),
        categories=tuple(tag.term for tag in entry.get("tags", [])),
    )
