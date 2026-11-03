from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import SecurityAlert, Vulnerability
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt
from weekly_ai_newsletter.services.text import truncate

DESCRIPTION_CHARS = 600


class SecurityPick(BaseModel):
    index: int
    summary: str


class SecuritySelection(BaseModel):
    picks: list[SecurityPick]


def merge_vulnerabilities(batches: Iterable[Sequence[Vulnerability]]) -> list[Vulnerability]:
    """One entry per id, exploited ones first; a flaw known to both sources keeps the
    first one's details and is exploited if either says so."""
    merged: dict[str, Vulnerability] = {}
    for batch in batches:
        for vuln in batch:
            known = merged.get(vuln.id)
            if known is None:
                merged[vuln.id] = vuln
            elif vuln.exploited and not known.exploited:
                merged[vuln.id] = replace(known, exploited=True)
    return sorted(merged.values(), key=lambda v: not v.exploited)


class SecurityCurator:
    """Claude writes up the most important flaws; every other exploited one is still listed."""

    def __init__(self, llm: LLMClient, *, language: str, max_items: int) -> None:
        self._llm = llm
        self._language = language
        self._max_items = max_items

    def curate(self, candidates: Sequence[Vulnerability]) -> list[SecurityAlert]:
        if not candidates:
            return []
        system = render_prompt(
            "curate_security.md.j2",
            language=LANGUAGE_NAMES[self._language],
            max_items=self._max_items,
        )
        prompt = json.dumps(
            [
                {
                    "index": index,
                    "id": vuln.id,
                    "exploited": vuln.exploited,
                    "affected": vuln.affected,
                    "title": vuln.title,
                    "description": truncate(vuln.description, DESCRIPTION_CHARS),
                    "fixed_in": vuln.fixed_in,
                }
                for index, vuln in enumerate(candidates)
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=SecuritySelection)
        highlights: list[SecurityAlert] = []
        used: set[int] = set()
        for pick in answer.picks:
            if len(highlights) == self._max_items:
                break
            if not 0 <= pick.index < len(candidates) or pick.index in used:
                continue
            used.add(pick.index)
            highlights.append(SecurityAlert(candidates[pick.index], pick.summary))
        rest = [vuln for index, vuln in enumerate(candidates) if index not in used]
        return highlights + self.brief(rest)

    @staticmethod
    def brief(candidates: Iterable[Vulnerability]) -> list[SecurityAlert]:
        """Exploited flaws listed without a write-up."""
        return [SecurityAlert(vuln) for vuln in candidates if vuln.exploited]
