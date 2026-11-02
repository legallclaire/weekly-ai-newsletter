from datetime import UTC, date, datetime

import httpx
import pytest

from weekly_ai_newsletter.adapters.github_search import GithubRepoSearchSource
from weekly_ai_newsletter.domain.errors import SourceError


def item(full_name: str, stars: int, topics: list[str]) -> dict[str, object]:
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": None,
        "stargazers_count": stars,
        "created_at": "2026-10-20T08:00:00Z",
        "topics": topics,
    }


def test_searches_each_topic_and_merges_results() -> None:
    requests: list[httpx.Request] = []
    by_topic = {
        "agent-skills": [item("a/skill", 900, ["agent-skills"]), item("b/both", 300, ["x"])],
        "mcp-server": [item("b/both", 300, ["mcp-server"]), item("c/mcp", 500, ["mcp-server"])],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        topic = request.url.params["q"].split()[0].removeprefix("topic:")
        return httpx.Response(200, json={"items": by_topic[topic]})

    source = GithubRepoSearchSource(
        httpx.Client(transport=httpx.MockTransport(handler)), token="t0k"
    )
    repos = source.search(
        ["agent-skills", "mcp-server"], created_after=date(2026, 10, 5), min_stars=50
    )

    assert [r.full_name for r in repos] == ["a/skill", "c/mcp", "b/both"]
    assert requests[0].url.params["q"] == "topic:agent-skills created:>=2026-10-05 stars:>=50"
    assert requests[0].url.params["sort"] == "stars"
    assert requests[0].headers["Authorization"] == "Bearer t0k"
    both = repos[2]
    assert both.topics == ("x", "mcp-server")
    assert both.description == ""
    assert both.created_at == datetime(2026, 10, 20, 8, tzinfo=UTC)


def test_search_failure_is_a_source_error() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(422, json={"message": "bad"}))
    source = GithubRepoSearchSource(httpx.Client(transport=transport), sleep=lambda _: None)
    with pytest.raises(SourceError):
        source.search(["mcp-server"], created_after=date(2026, 10, 5), min_stars=50)
