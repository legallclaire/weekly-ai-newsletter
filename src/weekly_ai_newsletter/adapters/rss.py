from __future__ import annotations

import calendar
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow


class RssFeedSource:
    """Items of one RSS/Atom feed published within a time window."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        response = get_with_retry(self._client, url)
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise SourceError(f"feed {name!r} could not be parsed: {feed.get('bozo_exception')}")
        items: list[FeedItem] = []
        for entry in feed.entries:
            published = _published(entry)
            link = entry.get("link")
            if published is None or not link or not window.contains(published):
                continue
            items.append(
                FeedItem(
                    title=html_to_text(entry.get("title", "")),
                    url=link,
                    summary=html_to_text(_body(entry)),
                    published=published,
                    source=name,
                )
            )
        return items


def html_to_text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    return " ".join(text.split())


def _published(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _body(entry: Any) -> str:
    if entry.get("content"):
        return str(entry.content[0].get("value", ""))
    return str(entry.get("summary", ""))
