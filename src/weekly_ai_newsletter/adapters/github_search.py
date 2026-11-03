from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, datetime

import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry, github_headers
from weekly_ai_newsletter.domain.errors import SourceError, describe_error
from weekly_ai_newsletter.domain.models import ExtensionRepo

SEARCH_URL = "https://api.github.com/search/repositories"
RESULTS_PER_TOPIC = 30


class GithubRepoSearchSource:
    """Recent repositories by topic, via the GitHub search API (one query per topic).

    Search qualifiers cannot OR topics together, so each topic is queried separately
    and the results merged.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        token: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._headers = github_headers(token)

    def search(
        self, topics: Sequence[str], *, created_after: date, min_stars: int
    ) -> list[ExtensionRepo]:
        repos: dict[str, ExtensionRepo] = {}
        for topic in topics:
            query = f"topic:{topic} created:>={created_after.isoformat()} stars:>={min_stars}"
            try:
                response = get_with_retry(
                    self._client,
                    SEARCH_URL,
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": RESULTS_PER_TOPIC,
                    },
                    headers=self._headers,
                    sleep=self._sleep,
                )
            except httpx.HTTPError as exc:
                raise SourceError(
                    f"GitHub search failed for topic {topic}: {describe_error(exc)}"
                ) from exc
            for raw in response.json().get("items", []):
                repo = _to_repo(raw)
                known = repos.get(repo.full_name)
                if known is not None:
                    merged = known.topics + tuple(t for t in repo.topics if t not in known.topics)
                    repo = replace(known, topics=merged)
                repos[repo.full_name] = repo
        return sorted(repos.values(), key=lambda r: (-r.stars, r.full_name))


def _to_repo(raw: dict[str, object]) -> ExtensionRepo:
    topics = raw.get("topics") or []
    return ExtensionRepo(
        full_name=str(raw["full_name"]),
        url=str(raw["html_url"]),
        description=str(raw.get("description") or ""),
        stars=int(str(raw.get("stargazers_count") or 0)),
        created_at=datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00")),
        topics=tuple(str(t) for t in topics) if isinstance(topics, list) else (),
    )
