from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import FeedItem, NewsItem
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt
from weekly_ai_newsletter.services.text import truncate

SUMMARY_CHARS = 600


class NewsPick(BaseModel):
    index: int
    summary: str


class NewsSelection(BaseModel):
    picks: list[NewsPick]


class NewsCurator:
    def __init__(self, llm: LLMClient, *, language: str, max_items: int) -> None:
        self._llm = llm
        self._language = language
        self._max_items = max_items

    def curate(self, items: Sequence[FeedItem]) -> list[NewsItem]:
        if not items:
            return []
        system = render_prompt(
            "curate_news.md.j2",
            language=LANGUAGE_NAMES[self._language],
            max_items=self._max_items,
        )
        prompt = json.dumps(
            [
                {
                    "index": index,
                    "source": item.source,
                    "title": item.title,
                    "summary": truncate(item.summary, SUMMARY_CHARS),
                }
                for index, item in enumerate(items)
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=NewsSelection)
        selected: list[NewsItem] = []
        used: set[int] = set()
        for pick in answer.picks:
            if not 0 <= pick.index < len(items) or pick.index in used:
                continue
            used.add(pick.index)
            item = items[pick.index]
            selected.append(
                NewsItem(title=item.title, url=item.url, source=item.source, summary=pick.summary)
            )
        return selected[: self._max_items]
