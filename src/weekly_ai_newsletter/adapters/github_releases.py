from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry, github_headers
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.ports import FeedSource

_RELEASES_FEED = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/releases\.atom$")
RELEASES_PER_PAGE = 30
MAX_PAGES = 5  # 150 releases: enough for one week of the busiest tools


class GithubReleasesSource:
    """Stable releases of a GitHub repository, via the REST API.

    GitHub's releases.atom feed is capped at 10 entries, which busy projects (with many
    pre-releases) exceed in a single week; the API lets us skip pre-releases and drafts.
    """

    def __init__(self, client: httpx.Client, *, token: str | None = None) -> None:
        self._client = client
        self._headers = github_headers(token)

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        match = _RELEASES_FEED.match(url)
        if match is None:
            raise ValueError(f"not a GitHub releases feed: {url}")
        owner, repo = match.groups()
        items: list[FeedItem] = []
        for page in range(1, MAX_PAGES + 1):
            releases = self._page(owner, repo, page)
            for release in releases:
                if release.get("draft") or not release.get("published_at"):
                    continue
                published = _published(release)
                if release.get("prerelease") or not window.contains(published):
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
            # Newest first: stop once a page is short or reaches back past the window.
            dated = [_published(r) for r in releases if r.get("published_at")]
            if len(releases) < RELEASES_PER_PAGE or (dated and min(dated) < window.start):
                break
        return items

    def _page(self, owner: str, repo: str, page: int) -> list[dict[str, Any]]:
        response = get_with_retry(
            self._client,
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            params={"per_page": RELEASES_PER_PAGE, "page": page},
            headers=self._headers,
        )
        releases: list[dict[str, Any]] = response.json()
        return releases


def _published(release: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))


class RoutingFeedSource:
    """Sends GitHub releases feeds to the API source and every other feed to RSS."""

    def __init__(self, *, rss: FeedSource, releases: FeedSource) -> None:
        self._rss = rss
        self._releases = releases

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        source = self._releases if _RELEASES_FEED.match(url) else self._rss
        return source.fetch(name, url, window)
