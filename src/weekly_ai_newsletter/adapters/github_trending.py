from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import httpx
from bs4 import BeautifulSoup

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError, describe_error
from weekly_ai_newsletter.domain.models import Repo

logger = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"
_STARS_THIS_WEEK = re.compile(r"([\d,]+)\s+stars\s+this\s+week")


class GithubTrendingSource:
    """Weekly trending repositories, scraped from github.com/trending (no official API)."""

    def __init__(self, client: httpx.Client, *, languages: Sequence[str] = ("", "python")) -> None:
        self._client = client
        self._languages = languages

    def fetch_weekly(self) -> list[Repo]:
        repos: dict[str, Repo] = {}
        failures: list[str] = []
        for language in self._languages:
            url = f"{TRENDING_URL}/{language}" if language else TRENDING_URL
            try:
                response = get_with_retry(self._client, url, params={"since": "weekly"})
                page = parse_trending_page(response.text)
            except (httpx.HTTPError, SourceError) as exc:  # other pages may still work
                logger.warning("Trending page %s failed: %s", url, exc)
                failures.append(f"{language or 'all'}: {describe_error(exc)}")
                continue
            for repo in page:
                repos.setdefault(repo.full_name, repo)
        if failures and not repos:
            raise SourceError(f"every trending page failed ({'; '.join(failures)})")
        return list(repos.values())


def parse_trending_page(html: str) -> list[Repo]:
    soup = BeautifulSoup(html, "html.parser")
    repos: list[Repo] = []
    for article in soup.select("article.Box-row"):
        link = article.select_one("h2 a[href]")
        if link is None:
            continue
        full_name = str(link["href"]).strip("/")
        description = article.select_one("p")
        language = article.select_one('[itemprop="programmingLanguage"]')
        stars = article.select_one('a[href$="/stargazers"]')
        this_week = _STARS_THIS_WEEK.search(" ".join(article.get_text(" ").split()))
        repos.append(
            Repo(
                full_name=full_name,
                url=f"https://github.com/{full_name}",
                description=" ".join(description.get_text().split()) if description else "",
                language=language.get_text(strip=True) if language else None,
                stars=_to_int(stars.get_text()) if stars else 0,
                stars_this_week=_to_int(this_week.group(1)) if this_week else 0,
            )
        )
    if not repos:
        raise SourceError("no repository found on the trending page; its layout may have changed")
    return repos


def _to_int(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0
