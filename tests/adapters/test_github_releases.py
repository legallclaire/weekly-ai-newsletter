from datetime import UTC, datetime

import httpx
import pytest

from tests.factories import make_feed_item
from weekly_ai_newsletter.adapters.github_releases import (
    RELEASES_PER_PAGE,
    GithubReleasesSource,
    RoutingFeedSource,
)
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow(datetime(2026, 10, 28, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC))
FEED_URL = "https://github.com/openai/codex/releases.atom"


def release(
    tag: str, published: str, *, prerelease: bool = False, draft: bool = False
) -> dict[str, object]:
    return {
        "tag_name": tag,
        "name": f"Release {tag}",
        "html_url": f"https://github.com/openai/codex/releases/tag/{tag}",
        "body": "## Features\n- New `sandbox` mode",
        "published_at": published,
        "prerelease": prerelease,
        "draft": draft,
    }


def test_lists_stable_releases_in_window_via_the_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                release("v0.3.0-alpha.1", "2026-11-01T10:00:00Z", prerelease=True),
                release("v0.2.0", "2026-10-30T10:00:00Z"),
                release("v0.2.1", "2026-10-31T10:00:00Z", draft=True),
                release("v0.1.0", "2026-10-01T10:00:00Z"),
            ],
        )

    source = GithubReleasesSource(httpx.Client(transport=httpx.MockTransport(handler)), token="t0k")
    [item] = source.fetch("OpenAI Codex", FEED_URL, WINDOW)

    assert str(requests[0].url).startswith("https://api.github.com/repos/openai/codex/releases")
    assert requests[0].headers["Authorization"] == "Bearer t0k"
    assert item.title == "Release v0.2.0"
    assert item.url == "https://github.com/openai/codex/releases/tag/v0.2.0"
    assert item.summary == "## Features\n- New `sandbox` mode"
    assert item.source == "OpenAI Codex"
    assert item.published == datetime(2026, 10, 30, 10, tzinfo=UTC)


def test_works_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=[])

    source = GithubReleasesSource(httpx.Client(transport=httpx.MockTransport(handler)))
    assert source.fetch("Codex", FEED_URL, WINDOW) == []


def test_rejects_non_release_urls() -> None:
    source = GithubReleasesSource(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )
    with pytest.raises(ValueError):
        source.fetch("Blog", "https://example.com/feed", WINDOW)


class RecordingSource:
    def __init__(self, label: str) -> None:
        self.label = label

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        return [make_feed_item(url, source=self.label)]


def test_routing_sends_github_release_feeds_to_the_api_and_others_to_rss() -> None:
    router = RoutingFeedSource(rss=RecordingSource("rss"), releases=RecordingSource("api"))
    assert router.fetch("Codex", FEED_URL, WINDOW)[0].source == "api"
    assert router.fetch("Blog", "https://blog.example/feed", WINDOW)[0].source == "rss"


def test_pages_through_releases_until_the_window_is_covered() -> None:
    pages = {
        "1": [
            release(f"v1.0.0-alpha.{n}", "2026-11-02T10:00:00Z", prerelease=True)
            for n in range(RELEASES_PER_PAGE)
        ],
        "2": [release("v0.9.0", "2026-10-30T10:00:00Z"), release("v0.8.0", "2026-10-01T10:00:00Z")]
        + [release(f"v0.7.{n}", "2026-09-01T10:00:00Z") for n in range(RELEASES_PER_PAGE - 2)],
        "3": [release("v0.1.0", "2026-10-29T10:00:00Z")],  # must not be requested
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        requested.append(page)
        return httpx.Response(200, json=pages[page])

    source = GithubReleasesSource(httpx.Client(transport=httpx.MockTransport(handler)))
    items = source.fetch("Codex", FEED_URL, WINDOW)
    assert [item.title for item in items] == ["Release v0.9.0"]
    assert requested == ["1", "2"]
