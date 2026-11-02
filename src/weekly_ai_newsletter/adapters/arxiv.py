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
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._page_size = page_size
        self._max_results = max_results
        self._delay = delay_seconds
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
            entries = feedparser.parse(response.text).entries
            for entry in entries:
                paper = _to_paper(entry)
                if window.contains(paper.published):
                    papers.setdefault(paper.arxiv_id, paper)
            if len(entries) < self._page_size:
                break
        return list(papers.values())


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
