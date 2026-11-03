from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import CuratedRepo, Repo
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt
from weekly_ai_newsletter.services.verdicts import kept_by_verdict


class RepoVerdict(BaseModel):
    full_name: str
    keep: bool
    why_interesting: str


class RepoVerdicts(BaseModel):
    verdicts: list[RepoVerdict]


class RepoCurator:
    def __init__(self, llm: LLMClient, *, language: str, max_items: int) -> None:
        self._llm = llm
        self._language = language
        self._max_items = max_items

    def curate(self, repos: Sequence[Repo]) -> list[CuratedRepo]:
        if not repos:
            return []
        system = render_prompt("curate_repos.md.j2", language=LANGUAGE_NAMES[self._language])
        prompt = json.dumps(
            [
                {
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "language": repo.language,
                    "stars_this_week": repo.stars_this_week,
                }
                for repo in repos
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=RepoVerdicts)
        kept = [
            CuratedRepo(repo=repo, why_interesting=why)
            for repo, why in kept_by_verdict(repos, answer.verdicts, name=lambda r: r.full_name)
        ]
        kept.sort(key=lambda c: (-c.repo.stars_this_week, c.repo.full_name))
        return kept[: self._max_items]
