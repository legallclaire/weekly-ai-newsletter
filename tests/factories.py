from datetime import UTC, datetime

from weekly_ai_newsletter.domain.models import FeedItem, Paper, PaperScore, Repo

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_paper(
    arxiv_id: str = "2610.00001",
    *,
    title: str = "A paper",
    abstract: str = "An abstract.",
    published: datetime = NOW,
) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=("Ada Lovelace",),
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published=published,
        categories=("cs.LG",),
    )


def make_score(
    arxiv_id: str = "2610.00001",
    *,
    relevance: int = 7,
    novelty: int = 7,
    evidence: int = 7,
    depth: int = 7,
    practical_utility: int = 7,
    is_incremental: bool = False,
) -> PaperScore:
    return PaperScore(
        arxiv_id=arxiv_id,
        relevance=relevance,
        novelty=novelty,
        evidence=evidence,
        depth=depth,
        practical_utility=practical_utility,
        is_incremental=is_incremental,
        rationale="Because.",
    )


def make_feed_item(
    url: str = "https://example.com/a",
    *,
    title: str = "Item",
    summary: str = "Summary",
    published: datetime = NOW,
    source: str = "Example",
) -> FeedItem:
    return FeedItem(title=title, url=url, summary=summary, published=published, source=source)


def make_repo(
    full_name: str = "acme/agent-kit",
    *,
    description: str = "An LLM agent framework",
    language: str | None = "Python",
    stars: int = 1000,
    stars_this_week: int = 300,
) -> Repo:
    return Repo(
        full_name=full_name,
        url=f"https://github.com/{full_name}",
        description=description,
        language=language,
        stars=stars,
        stars_this_week=stars_this_week,
    )
