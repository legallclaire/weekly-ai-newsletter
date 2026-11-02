from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import CuratedExtension, ExtensionRepo
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt


class ExtensionVerdict(BaseModel):
    full_name: str
    keep: bool
    why_interesting: str


class ExtensionVerdicts(BaseModel):
    verdicts: list[ExtensionVerdict]


class ExtensionCurator:
    """Keeps useful skills, plugins and MCP servers; MCP servers are capped."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        language: str,
        max_items: int,
        max_mcp: int,
        mcp_topics: Sequence[str],
    ) -> None:
        self._llm = llm
        self._language = language
        self._max_items = max_items
        self._max_mcp = max_mcp
        self._mcp_topics = frozenset(mcp_topics)

    def curate(self, repos: Sequence[ExtensionRepo]) -> list[CuratedExtension]:
        if not repos:
            return []
        system = render_prompt("curate_extensions.md.j2", language=LANGUAGE_NAMES[self._language])
        prompt = json.dumps(
            [
                {
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "topics": list(repo.topics),
                    "stars": repo.stars,
                }
                for repo in repos
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=ExtensionVerdicts)
        pending = {repo.full_name: repo for repo in repos}
        kept: list[CuratedExtension] = []
        for verdict in answer.verdicts:
            repo = pending.pop(verdict.full_name, None)
            if repo is not None and verdict.keep:
                is_mcp = not self._mcp_topics.isdisjoint(repo.topics)
                kept.append(CuratedExtension(repo, verdict.why_interesting, is_mcp))
        kept.sort(key=lambda c: (-c.repo.stars, c.repo.full_name))
        selected: list[CuratedExtension] = []
        mcp_count = 0
        for candidate in kept:
            if candidate.is_mcp:
                if mcp_count >= self._max_mcp:
                    continue
                mcp_count += 1
            selected.append(candidate)
        return selected[: self._max_items]
