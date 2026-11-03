from pathlib import Path

import httpx
import pytest

from weekly_ai_newsletter.adapters.github_trending import GithubTrendingSource, parse_trending_page
from weekly_ai_newsletter.domain.errors import SourceError

FIXTURE = (Path(__file__).parents[1] / "fixtures" / "github_trending.html").read_text()


def test_parses_repositories_from_trending_page() -> None:
    first, second = parse_trending_page(FIXTURE)
    assert first.full_name == "acme/agent-kit"
    assert first.url == "https://github.com/acme/agent-kit"
    assert first.description == "Build reliable LLM agents"
    assert first.language == "Python"
    assert (first.stars, first.stars_this_week) == (12345, 2345)
    assert second.full_name == "someone/awesome-llm"
    assert (second.description, second.language, second.stars_this_week) == ("", None, 150)


def test_page_without_repositories_signals_a_layout_change() -> None:
    with pytest.raises(SourceError, match="layout"):
        parse_trending_page("<html><body>nothing here</body></html>")


def test_fetches_each_language_and_dedupes() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.url.path}?{request.url.query.decode()}")
        return httpx.Response(200, text=FIXTURE)

    source = GithubTrendingSource(
        httpx.Client(transport=httpx.MockTransport(handler)), languages=("", "python")
    )
    repos = source.fetch_weekly()
    assert paths == ["/trending?since=weekly", "/trending/python?since=weekly"]
    assert [r.full_name for r in repos] == ["acme/agent-kit", "someone/awesome-llm"]


def test_one_failing_language_page_keeps_the_others() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/trending/python":
            return httpx.Response(404)
        return httpx.Response(200, text=FIXTURE)

    source = GithubTrendingSource(
        httpx.Client(transport=httpx.MockTransport(handler)), languages=("", "python")
    )
    assert [r.full_name for r in source.fetch_weekly()] == ["acme/agent-kit", "someone/awesome-llm"]


def test_every_language_page_failing_is_a_source_error() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html></html>"))
    source = GithubTrendingSource(httpx.Client(transport=transport), languages=("", "python"))
    with pytest.raises(SourceError):
        source.fetch_weekly()
