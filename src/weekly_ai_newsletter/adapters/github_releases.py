from __future__ import annotations

import re
from datetime import datetime

import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.ports import FeedSource

_RELEASES_FEED = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/releases\.atom$")
RELEASES_PER_PAGE = 30


class GithubReleasesSource:
    """Stable releases of a GitHub repository, via the REST API.

    GitHub's releases.atom feed is capped at 10 entries, which busy projects (with many
    pre-releases) exceed in a single week; the API lets us skip pre-releases and drafts.
    """

    def __init__(self, client: httpx.Client, *, token: str | None = None) -> None:
        self._client = client
        self._headers = {"Accept": "application/vnd.github+json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        match = _RELEASES_FEED.match(url)
        if match is None:
            raise ValueError(f"not a GitHub releases feed: {url}")
        owner, repo = match.groups()
        response = get_with_retry(
            self._client,
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            params={"per_page": RELEASES_PER_PAGE},
            headers=self._headers,
        )
        items: list[FeedItem] = []
        for release in response.json():
            if release.get("draft") or release.get("prerelease") or not release.get("published_at"):
                continue
            published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
            if not window.contains(published):
                continue
            items.append(
                FeedItem(
                    title=release.get("name") or release["tag_name"],
                    url=release["html_url"],
                    summary=release.get("body") or "",
                    published=published,
                    source=name,
                )
            )
        return items


class RoutingFeedSource:
    """Sends GitHub releases feeds to the API source and every other feed to RSS."""

    def __init__(self, *, rss: FeedSource, releases: FeedSource) -> None:
        self._rss = rss
        self._releases = releases

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        source = self._releases if _RELEASES_FEED.match(url) else self._rss
        return source.fetch(name, url, window)
