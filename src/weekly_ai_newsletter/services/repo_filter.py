from __future__ import annotations

from collections.abc import Iterable

from weekly_ai_newsletter.config import RepoKeywords
from weekly_ai_newsletter.domain.models import Repo
from weekly_ai_newsletter.services.text import keyword_pattern


class RepoRuleFilter:
    """Deterministic first pass over trending repos, before any LLM call."""

    def __init__(self, keywords: RepoKeywords) -> None:
        self._include = [keyword_pattern(term) for term in keywords.include]
        self._exclude = [term.lower() for term in keywords.exclude]

    def keep(self, repo: Repo) -> bool:
        if repo.language is None:  # lists and docs-only repos have no detected language
            return False
        name = repo.full_name.rsplit("/", 1)[-1].lower()
        if any(term in name for term in self._exclude):
            return False
        haystack = f"{repo.full_name} {repo.description}"
        return any(pattern.search(haystack) for pattern in self._include)

    def apply(self, repos: Iterable[Repo]) -> list[Repo]:
        return [repo for repo in repos if self.keep(repo)]
