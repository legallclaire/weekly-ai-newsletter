from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import DevToolChange, DevToolGroup, FeedItem
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt
from weekly_ai_newsletter.services.text import truncate

CONTENT_CHARS = 1500


class ChangePick(BaseModel):
    index: int
    summary: str


class ToolGroup(BaseModel):
    tool: str
    changes: list[ChangePick]


class DevToolsSelection(BaseModel):
    groups: list[ToolGroup]


class DevToolsCurator:
    def __init__(self, llm: LLMClient, *, language: str) -> None:
        self._llm = llm
        self._language = language

    def curate(self, items: Sequence[FeedItem]) -> list[DevToolGroup]:
        if not items:
            return []
        system = render_prompt("curate_devtools.md.j2", language=LANGUAGE_NAMES[self._language])
        prompt = json.dumps(
            [
                {
                    "index": index,
                    "source": item.source,
                    "title": item.title,
                    "content": truncate(item.summary, CONTENT_CHARS),
                }
                for index, item in enumerate(items)
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=DevToolsSelection)
        groups: list[DevToolGroup] = []
        used: set[int] = set()
        for group in answer.groups:
            changes: list[DevToolChange] = []
            for pick in group.changes:
                if not 0 <= pick.index < len(items) or pick.index in used:
                    continue
                used.add(pick.index)
                item = items[pick.index]
                changes.append(DevToolChange(title=item.title, url=item.url, summary=pick.summary))
            if changes:
                groups.append(DevToolGroup(tool=group.tool, changes=tuple(changes)))
        return groups
