# Weekly AI Newsletter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python pipeline, run weekly by GitHub Actions, that collects AI news, AI dev-tool releases, arXiv papers and GitHub trending repos, curates them with Claude, and emails an HTML newsletter via Resend every Wednesday at 07:00 Europe/Paris.

**Architecture:** Ports & adapters. Pure domain models and services (keyword filter, score aggregation, selection, dedup) depend only on `Protocol` ports; concrete adapters (arXiv, RSS, GitHub Trending, Claude, Resend, JSON history) are wired in one composition root. The pipeline builds four independent sections (a failing section degrades to a notice), renders HTML + text with Jinja2, then publishes (send, archive, record history).

**Tech Stack:** Python 3.12, uv, Pydantic v2, httpx, feedparser, beautifulsoup4, PyYAML, Jinja2, anthropic SDK, pytest, ruff, mypy (strict), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-02-ai-newsletter-design.md`

## Global Constraints

- Python `>=3.12`; package name `weekly_ai_newsletter`, `src/` layout, CLI entry point `newsletter`.
- All code, comments, identifiers, docs and commit messages in English. Newsletter text language is configurable: `language: fr` (default) or `en`.
- `mypy --strict` must pass on `src` and `tests`; `ruff check` and `ruff format --check` must pass (line length 100).
- Tests never touch the network (use `httpx.MockTransport`, fakes, inline fixtures).
- Paper total = `2·relevance + 2·novelty + evidence + depth + practical_utility` (max 70), computed in Python, never by the LLM.
- Paper selection defaults: drop `is_incremental` or `novelty < 6`, drop `total < 45`, keep at most 3, tie-break `relevance + novelty` then `arxiv_id`.
- Defaults: `prefilter_size 50`, `batch_size 10`, `news.max_items 6`, `repos.max_items 5`, `repos.repeat_after_weeks 8`, `window_lag_days 2`, model `claude-sonnet-5-5`.
- arXiv categories default: `cs.LG, cs.AI, cs.CL, stat.ML, cs.IR, cs.MA, cs.SE, cs.DC`; ≥ 3 s between arXiv requests.
- Secrets only from env: `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`, `RECIPIENT_EMAIL`. Never logged.
- URLs shown in the newsletter always come from source data, never from LLM output (the LLM returns indices/IDs).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Git identity is already set repo-locally (`legallclaire`). Never push without the user's explicit approval.

## Review Focus

1. **Feed entries without a date or link** (common in real RSS) → skipped silently, never crash the section. Pinned in Task 11.
2. **LLM returns unknown/duplicate/out-of-range IDs or indices** → ignored; URLs never invented. Pinned in Tasks 6, 7, 8.
3. **A quiet week (zero arXiv papers, zero fresh news)** → section renders "nothing this week", not "unavailable", and the run still succeeds. Pinned in Task 16.
4. **Two scheduled triggers on the same Wednesday** (delayed cron) → second run does nothing because today's archive exists. Pinned in Task 17.
5. **HTML/special characters in titles and summaries** (`<`, `&`, accents) → escaped in the HTML email, readable in the text version. Pinned in Task 15.

---

## File map

```
pyproject.toml, uv.lock, .gitignore, .env.example, LICENSE, README.md, .pre-commit-config.yaml
.github/workflows/ci.yml, .github/workflows/newsletter.yml
config/settings.yaml, config/sources.yaml, config/keywords.yaml
state/.gitkeep, archive/.gitkeep
src/weekly_ai_newsletter/
  __init__.py
  domain/__init__.py, window.py, models.py, newsletter.py, history.py, errors.py
  ports.py
  config.py
  prompts/__init__.py, score_papers.md.j2, write_papers.md.j2, curate_news.md.j2,
          curate_devtools.md.j2, curate_repos.md.j2
  services/__init__.py, text.py, keyword_filter.py, paper_selection.py, paper_scorer.py,
           paper_writer.py, news_curator.py, devtools_curator.py, repo_filter.py,
           repo_curator.py, dedup.py
  adapters/__init__.py, http.py, arxiv.py, rss.py, github_trending.py, claude.py,
           resend.py, json_history.py
  rendering/__init__.py, renderer.py, templates/newsletter.html.j2, templates/newsletter.txt.j2
  pipeline.py, bootstrap.py, scheduling.py, cli.py
tests/__init__.py, factories.py, fakes.py
tests/unit/…, tests/adapters/…, tests/pipeline/… (each with __init__.py)
tests/fixtures/github_trending.html
```

---

### Task 1: Project scaffolding and CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `src/weekly_ai_newsletter/__init__.py`, `tests/__init__.py`, `tests/test_package.py`

**Interfaces:**
- Produces: importable package `weekly_ai_newsletter` with `__version__ = "0.1.0"`; `uv run pytest|ruff|mypy` work.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "weekly-ai-newsletter"
version = "0.1.0"
description = "A weekly AI digest (news, dev tools, research papers, trending repos) curated with Claude and delivered by email."
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
authors = [{ name = "legallclaire" }]
dependencies = [
    "anthropic>=0.40",
    "beautifulsoup4>=4.12",
    "feedparser>=6.0",
    "httpx>=0.27",
    "jinja2>=3.1",
    "pydantic>=2.7",
    "pyyaml>=6.0",
]

[project.scripts]
newsletter = "weekly_ai_newsletter.cli:main"

[dependency-groups]
dev = [
    "mypy>=1.11",
    "pre-commit>=3.8",
    "pytest>=8.3",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "types-PyYAML",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.mypy]
strict = true
python_version = "3.12"

[[tool.mypy.overrides]]
module = ["feedparser"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

- [ ] **Step 2: Write supporting files**

`.gitignore`:
```gitignore
__pycache__/
*.py[cod]
.venv/
.env
.coverage
htmlcov/
.mypy_cache/
.pytest_cache/
.ruff_cache/
dist/
preview.html
```

`.env.example`:
```dotenv
# Copy to .env and run: uv run --env-file .env newsletter run --dry-run
ANTHROPIC_API_KEY=sk-ant-...
# Only needed to actually send (not for --dry-run)
RESEND_API_KEY=re_...
SENDER_EMAIL=onboarding@resend.dev
RECIPIENT_EMAIL=you@example.com
```

`LICENSE`: standard MIT license text, `Copyright (c) 2026 legallclaire`.

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: mypy
        name: mypy
        entry: uv run mypy src tests
        language: system
        types: [python]
        pass_filenames: false
```

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src tests
      - run: uv run pytest --cov=weekly_ai_newsletter --cov-report=term-missing
```

`src/weekly_ai_newsletter/__init__.py`:
```python
"""Weekly AI newsletter: collect, curate with Claude, and deliver by email."""

__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 3: Write the smoke test**

`tests/test_package.py`:
```python
import weekly_ai_newsletter


def test_package_exposes_version() -> None:
    assert weekly_ai_newsletter.__version__ == "0.1.0"
```

- [ ] **Step 4: Install and run all checks**

Run: `uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests`
Expected: `1 passed`, ruff and mypy report no issues. `uv.lock` is created.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .env.example LICENSE .pre-commit-config.yaml .github src tests
git commit -m "chore: scaffold project with uv, ruff, mypy, pytest and CI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Domain models, errors and ports

**Files:**
- Create: `src/weekly_ai_newsletter/domain/__init__.py` (empty), `domain/window.py`, `domain/models.py`, `domain/newsletter.py`, `domain/history.py`, `domain/errors.py`, `src/weekly_ai_newsletter/ports.py`, `tests/factories.py`, `tests/unit/__init__.py` (empty), `tests/unit/test_domain.py`

**Interfaces:**
- Produces:
  - `TimeWindow(start: datetime, end: datetime)`, `.contains(moment) -> bool`, `TimeWindow.week_before(run_date: date, *, lag_days: int = 0) -> TimeWindow`
  - `Paper(arxiv_id, title, abstract, authors: tuple[str, ...], url, published: datetime, categories: tuple[str, ...])`
  - `PaperScore` (Pydantic: `arxiv_id, relevance, novelty, evidence, depth, practical_utility` ints 1–10, `is_incremental: bool`, `rationale: str`, property `total: int`), constant `MAX_TOTAL = 70`
  - `ScoredPaper(paper, score)`, `SelectedPaper(paper, score, summary, why_selected)`
  - `FeedItem(title, url, summary, published, source)`, `NewsItem(title, url, source, summary)`
  - `DevToolChange(title, url, summary)`, `DevToolGroup(tool, changes: tuple[DevToolChange, ...])`
  - `Repo(full_name, url, description, language: str | None, stars, stars_this_week)`, `CuratedRepo(repo, why_interesting)`
  - `OutgoingEmail(sender, recipient, subject, html, text, idempotency_key)`
  - `Section[T](items: tuple[T, ...] = (), error: str | None = None)`, `.available`, `Section.ok(items)`, `Section.unavailable(error)`
  - `Newsletter(issue_date, language, news, devtools, papers, repos)`, `.sections -> dict[str, Section[Any]]`, `.all_unavailable -> bool`
  - `HistoryKind` (`PAPER="papers"`, `NEWS="news"`, `DEVTOOL="devtools"`, `REPO="repos"`), `History(entries)`, `.was_sent(kind, key, *, on_or_after=None)`, `.record(kind, keys, on)`
  - Errors: `NewsletterError` ⊃ `ConfigError`, `SourceError`, `LLMOutputError`, `EmailDeliveryError`, `PipelineError`
  - Ports (Protocols): `PaperSource.fetch(categories, window) -> list[Paper]`, `FeedSource.fetch(name, url, window) -> list[FeedItem]`, `TrendingSource.fetch_weekly() -> list[Repo]`, `LLMClient.structured(*, system, prompt, output_model: type[M]) -> M`, `EmailSender.send(message: OutgoingEmail) -> None`, `HistoryStore.load() -> History`, `HistoryStore.save(history) -> None`
  - Test helpers in `tests/factories.py`: `NOW`, `make_paper`, `make_score`, `make_feed_item`, `make_repo`

- [ ] **Step 1: Write the test helpers**

`tests/factories.py`:
```python
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
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_domain.py`:
```python
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from tests.factories import make_score
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.domain.newsletter import Newsletter, Section
from weekly_ai_newsletter.domain.window import TimeWindow


def test_week_before_ends_at_midnight_utc_of_run_date() -> None:
    window = TimeWindow.week_before(date(2026, 11, 4))
    assert window.start == datetime(2026, 10, 28, tzinfo=UTC)
    assert window.end == datetime(2026, 11, 4, tzinfo=UTC)


def test_week_before_with_lag_shifts_window_back() -> None:
    window = TimeWindow.week_before(date(2026, 11, 4), lag_days=2)
    assert window.start == datetime(2026, 10, 26, tzinfo=UTC)
    assert window.end == datetime(2026, 11, 2, tzinfo=UTC)


def test_window_is_half_open() -> None:
    window = TimeWindow.week_before(date(2026, 11, 4))
    assert window.contains(window.start)
    assert not window.contains(window.end)


def test_window_rejects_naive_or_inverted_bounds() -> None:
    with pytest.raises(ValueError):
        TimeWindow(datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=UTC))
    with pytest.raises(ValueError):
        TimeWindow(datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))


def test_score_total_doubles_relevance_and_novelty() -> None:
    score = make_score(relevance=9, novelty=8, evidence=7, depth=6, practical_utility=5)
    assert score.total == 2 * 9 + 2 * 8 + 7 + 6 + 5


@pytest.mark.parametrize("bad", [0, 11])
def test_score_rejects_out_of_range_values(bad: int) -> None:
    with pytest.raises(ValidationError):
        make_score(novelty=bad)


def test_section_states() -> None:
    ok: Section[int] = Section.ok([1, 2])
    broken: Section[int] = Section.unavailable("boom")
    assert ok.available and ok.items == (1, 2)
    assert not broken.available and broken.items == ()


def test_newsletter_all_unavailable() -> None:
    broken: Section[object] = Section.unavailable("x")
    newsletter = Newsletter(
        issue_date=date(2026, 11, 4),
        language="fr",
        news=broken,
        devtools=broken,
        papers=broken,
        repos=broken,
    )
    assert newsletter.all_unavailable
    assert list(newsletter.sections) == ["news", "devtools", "papers", "repos"]


def test_history_records_and_checks_with_cutoff() -> None:
    history = History()
    history.record(HistoryKind.REPO, ["acme/agent-kit"], date(2026, 9, 1))
    assert history.was_sent(HistoryKind.REPO, "acme/agent-kit")
    assert not history.was_sent(HistoryKind.REPO, "acme/agent-kit", on_or_after=date(2026, 10, 1))
    assert not history.was_sent(HistoryKind.NEWS, "acme/agent-kit")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weekly_ai_newsletter.domain'`

- [ ] **Step 4: Implement the domain**

`src/weekly_ai_newsletter/domain/errors.py`:
```python
class NewsletterError(Exception):
    """Base class for expected, reportable failures."""


class ConfigError(NewsletterError):
    """Invalid or missing configuration or secrets."""


class SourceError(NewsletterError):
    """A content source could not be fetched or parsed."""


class LLMOutputError(NewsletterError):
    """The LLM did not return valid structured output."""


class EmailDeliveryError(NewsletterError):
    """The email provider rejected or failed to receive the message."""


class PipelineError(NewsletterError):
    """The pipeline cannot produce or publish a newsletter."""
```

`src/weekly_ai_newsletter/domain/window.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class TimeWindow:
    """Half-open time interval [start, end) with timezone-aware bounds."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeWindow bounds must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("TimeWindow start must be before end")

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    @classmethod
    def week_before(cls, run_date: date, *, lag_days: int = 0) -> TimeWindow:
        end = datetime.combine(run_date - timedelta(days=lag_days), time.min, tzinfo=UTC)
        return cls(start=end - timedelta(days=7), end=end)
```

`src/weekly_ai_newsletter/domain/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_TOTAL = 70


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: tuple[str, ...]
    url: str
    published: datetime
    categories: tuple[str, ...]


class PaperScore(BaseModel):
    """Per-criterion scores produced by the LLM; the total is computed here."""

    model_config = ConfigDict(frozen=True)

    arxiv_id: str
    relevance: int = Field(ge=1, le=10)
    novelty: int = Field(ge=1, le=10)
    evidence: int = Field(ge=1, le=10)
    depth: int = Field(ge=1, le=10)
    practical_utility: int = Field(ge=1, le=10)
    is_incremental: bool
    rationale: str

    @property
    def total(self) -> int:
        return (
            2 * self.relevance
            + 2 * self.novelty
            + self.evidence
            + self.depth
            + self.practical_utility
        )


@dataclass(frozen=True)
class ScoredPaper:
    paper: Paper
    score: PaperScore


@dataclass(frozen=True)
class SelectedPaper:
    paper: Paper
    score: PaperScore
    summary: str
    why_selected: str


@dataclass(frozen=True)
class FeedItem:
    title: str
    url: str
    summary: str
    published: datetime
    source: str


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    summary: str


@dataclass(frozen=True)
class DevToolChange:
    title: str
    url: str
    summary: str


@dataclass(frozen=True)
class DevToolGroup:
    tool: str
    changes: tuple[DevToolChange, ...]


@dataclass(frozen=True)
class Repo:
    full_name: str
    url: str
    description: str
    language: str | None
    stars: int
    stars_this_week: int


@dataclass(frozen=True)
class CuratedRepo:
    repo: Repo
    why_interesting: str


@dataclass(frozen=True)
class OutgoingEmail:
    sender: str
    recipient: str
    subject: str
    html: str
    text: str
    idempotency_key: str
```

`src/weekly_ai_newsletter/domain/newsletter.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from weekly_ai_newsletter.domain.models import CuratedRepo, DevToolGroup, NewsItem, SelectedPaper


@dataclass(frozen=True)
class Section[T]:
    """Items of one newsletter section, or the reason it is unavailable."""

    items: tuple[T, ...] = ()
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.error is None

    @classmethod
    def ok(cls, items: Iterable[T]) -> Section[T]:
        return cls(items=tuple(items))

    @classmethod
    def unavailable(cls, error: str) -> Section[T]:
        return cls(error=error)


@dataclass(frozen=True)
class Newsletter:
    issue_date: date
    language: str
    news: Section[NewsItem]
    devtools: Section[DevToolGroup]
    papers: Section[SelectedPaper]
    repos: Section[CuratedRepo]

    @property
    def sections(self) -> dict[str, Section[Any]]:
        return {
            "news": self.news,
            "devtools": self.devtools,
            "papers": self.papers,
            "repos": self.repos,
        }

    @property
    def all_unavailable(self) -> bool:
        return not any(section.available for section in self.sections.values())
```

Note: `test_newsletter_all_unavailable` passes `Section[object]` to fields typed `Section[NewsItem]` etc. If mypy rejects this (invariance), change the test to build `Section.unavailable("x")` inline for each field instead of sharing one variable.

`src/weekly_ai_newsletter/domain/history.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class HistoryKind(StrEnum):
    PAPER = "papers"
    NEWS = "news"
    DEVTOOL = "devtools"
    REPO = "repos"


@dataclass
class History:
    """What was already sent, and when, keyed by kind then item key."""

    entries: dict[HistoryKind, dict[str, date]] = field(default_factory=dict)

    def was_sent(self, kind: HistoryKind, key: str, *, on_or_after: date | None = None) -> bool:
        sent_on = self.entries.get(kind, {}).get(key)
        if sent_on is None:
            return False
        return on_or_after is None or sent_on >= on_or_after

    def record(self, kind: HistoryKind, keys: Iterable[str], on: date) -> None:
        bucket = self.entries.setdefault(kind, {})
        for key in keys:
            bucket[key] = on
```

`src/weekly_ai_newsletter/ports.py`:
```python
"""Interfaces between the core logic and the outside world."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from weekly_ai_newsletter.domain.history import History
from weekly_ai_newsletter.domain.models import FeedItem, OutgoingEmail, Paper, Repo
from weekly_ai_newsletter.domain.window import TimeWindow


class PaperSource(Protocol):
    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]: ...


class FeedSource(Protocol):
    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]: ...


class TrendingSource(Protocol):
    def fetch_weekly(self) -> list[Repo]: ...


class LLMClient(Protocol):
    def structured[M: BaseModel](
        self, *, system: str, prompt: str, output_model: type[M]
    ) -> M:
        """Return the model's answer parsed and validated as `output_model`.

        Raises LLMOutputError when no valid output could be obtained.
        """
        ...


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


class HistoryStore(Protocol):
    def load(self) -> History: ...

    def save(self, history: History) -> None: ...
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit/test_domain.py -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS, no type or lint errors.

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "feat: add domain models, errors and ports

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Configuration and default config files

**Files:**
- Create: `src/weekly_ai_newsletter/config.py`, `config/settings.yaml`, `config/sources.yaml`, `config/keywords.yaml`, `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `ConfigError` (Task 2).
- Produces: `LLMSettings(model, max_tokens)`, `PaperSettings(categories, window_lag_days, prefilter_size, batch_size, min_total, min_novelty, max_selected)`, `NewsSettings(max_items, max_candidates)`, `DevToolsSettings(max_candidates)`, `RepoSettings(max_items, repeat_after_weeks, trending_languages)`, `Settings(language, llm, papers, news, devtools, repos, history_path, archive_dir)`, `FeedConfig(name, url)`, `Sources(news, devtools)`, `PaperKeywords(title_weight, positive, negative)`, `RepoKeywords(include, exclude)`, `Keywords(papers, repos)`, `EmailSecrets(resend_api_key, sender_email, recipient_email)`, `Secrets(anthropic_api_key, email)`, `Secrets.from_env(env, *, require_email) -> Secrets`, `AppConfig(settings, sources, keywords)`, `load_config(config_dir: Path) -> AppConfig`, `Language = Literal["fr", "en"]`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_config.py`:
```python
from pathlib import Path

import pytest

from weekly_ai_newsletter.config import Secrets, load_config
from weekly_ai_newsletter.domain.errors import ConfigError

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def test_shipped_config_is_valid_and_matches_spec_defaults() -> None:
    config = load_config(REPO_CONFIG)
    assert config.settings.language == "fr"
    assert config.settings.llm.model == "claude-sonnet-5-5"
    papers = config.settings.papers
    assert papers.categories == [
        "cs.LG", "cs.AI", "cs.CL", "stat.ML", "cs.IR", "cs.MA", "cs.SE", "cs.DC",
    ]
    assert (papers.prefilter_size, papers.batch_size) == (50, 10)
    assert (papers.min_total, papers.min_novelty, papers.max_selected) == (45, 6, 3)
    assert config.settings.repos.repeat_after_weeks == 8
    assert any(feed.name == "Claude Code" for feed in config.sources.devtools)
    assert config.keywords.papers.positive["agent"] > 0


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    for name in ("settings.yaml", "sources.yaml", "keywords.yaml"):
        (tmp_path / name).write_text((REPO_CONFIG / name).read_text())
    (tmp_path / "settings.yaml").write_text("langage: fr\n")
    with pytest.raises(ConfigError, match="settings"):
        load_config(tmp_path)


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="settings.yaml"):
        load_config(tmp_path)


def test_secrets_require_email_vars_only_when_sending() -> None:
    secrets = Secrets.from_env({"ANTHROPIC_API_KEY": "k"}, require_email=False)
    assert secrets.email is None
    with pytest.raises(ConfigError, match="RESEND_API_KEY"):
        Secrets.from_env({"ANTHROPIC_API_KEY": "k"}, require_email=True)


def test_secrets_are_not_exposed_in_repr() -> None:
    env = {
        "ANTHROPIC_API_KEY": "sk-secret",
        "RESEND_API_KEY": "re-secret",
        "SENDER_EMAIL": "a@b.c",
        "RECIPIENT_EMAIL": "d@e.f",
    }
    secrets = Secrets.from_env(env, require_email=True)
    assert "sk-secret" not in repr(secrets) and "re-secret" not in repr(secrets)
    assert secrets.email is not None
    assert secrets.email.resend_api_key.get_secret_value() == "re-secret"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weekly_ai_newsletter.config'`

- [ ] **Step 3: Implement `config.py`**

```python
"""Typed configuration loaded from config/*.yaml and secrets from the environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from weekly_ai_newsletter.domain.errors import ConfigError

Language = Literal["fr", "en"]

DEFAULT_CATEGORIES = ["cs.LG", "cs.AI", "cs.CL", "stat.ML", "cs.IR", "cs.MA", "cs.SE", "cs.DC"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMSettings(_Strict):
    model: str = "claude-sonnet-5-5"
    max_tokens: int = Field(default=8192, gt=0)


class PaperSettings(_Strict):
    categories: list[str] = Field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    window_lag_days: int = Field(default=2, ge=0)
    prefilter_size: int = Field(default=50, gt=0)
    batch_size: int = Field(default=10, gt=0)
    min_total: int = Field(default=45, ge=0, le=70)
    min_novelty: int = Field(default=6, ge=1, le=10)
    max_selected: int = Field(default=3, ge=0)


class NewsSettings(_Strict):
    max_items: int = Field(default=6, gt=0)
    max_candidates: int = Field(default=80, gt=0)


class DevToolsSettings(_Strict):
    max_candidates: int = Field(default=60, gt=0)


class RepoSettings(_Strict):
    max_items: int = Field(default=5, gt=0)
    repeat_after_weeks: int = Field(default=8, ge=0)
    trending_languages: list[str] = Field(default_factory=lambda: ["", "python"])


class Settings(_Strict):
    language: Language = "fr"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    papers: PaperSettings = Field(default_factory=PaperSettings)
    news: NewsSettings = Field(default_factory=NewsSettings)
    devtools: DevToolsSettings = Field(default_factory=DevToolsSettings)
    repos: RepoSettings = Field(default_factory=RepoSettings)
    history_path: Path = Path("state/history.json")
    archive_dir: Path = Path("archive")


class FeedConfig(_Strict):
    name: str
    url: str


class Sources(_Strict):
    news: list[FeedConfig]
    devtools: list[FeedConfig]


class PaperKeywords(_Strict):
    title_weight: float = 2.0
    positive: dict[str, float]
    negative: dict[str, float] = Field(default_factory=dict)


class RepoKeywords(_Strict):
    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class Keywords(_Strict):
    papers: PaperKeywords
    repos: RepoKeywords


class EmailSecrets(_Strict):
    resend_api_key: SecretStr
    sender_email: str
    recipient_email: str


class Secrets(_Strict):
    anthropic_api_key: SecretStr
    email: EmailSecrets | None

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, require_email: bool) -> Secrets:
        email_vars = ("RESEND_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAIL")
        required = ["ANTHROPIC_API_KEY", *(email_vars if require_email else ())]
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ConfigError(f"missing environment variables: {', '.join(missing)}")
        email = None
        if all(env.get(name) for name in email_vars):
            email = EmailSecrets(
                resend_api_key=SecretStr(env["RESEND_API_KEY"]),
                sender_email=env["SENDER_EMAIL"],
                recipient_email=env["RECIPIENT_EMAIL"],
            )
        return cls(anthropic_api_key=SecretStr(env["ANTHROPIC_API_KEY"]), email=email)


@dataclass(frozen=True)
class AppConfig:
    settings: Settings
    sources: Sources
    keywords: Keywords


def load_config(config_dir: Path) -> AppConfig:
    return AppConfig(
        settings=_load(config_dir / "settings.yaml", Settings),
        sources=_load(config_dir / "sources.yaml", Sources),
        keywords=_load(config_dir / "keywords.yaml", Keywords),
    )


def _load[C: BaseModel](path: Path, model: type[C]) -> C:
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid {path.name}: {exc}") from exc
```

- [ ] **Step 4: Write the default config files**

`config/settings.yaml`:
```yaml
# Newsletter text language: fr or en (code and logs are always English).
language: fr

llm:
  model: claude-sonnet-5-5
  max_tokens: 8192

papers:
  categories: [cs.LG, cs.AI, cs.CL, stat.ML, cs.IR, cs.MA, cs.SE, cs.DC]
  # arXiv announces submissions with a delay; shift the paper window back.
  window_lag_days: 2
  prefilter_size: 50
  batch_size: 10
  min_total: 45      # out of 70
  min_novelty: 6     # out of 10
  max_selected: 3

news:
  max_items: 6
  max_candidates: 80

devtools:
  max_candidates: 60

repos:
  max_items: 5
  repeat_after_weeks: 8
  trending_languages: ["", python]   # "" = all languages

history_path: state/history.json
archive_dir: archive
```

`config/sources.yaml`:
```yaml
# RSS/Atom feeds fetched every week; items outside the 7-day window are ignored.
news:
  - name: OpenAI
    url: https://openai.com/news/rss.xml
  - name: Google DeepMind
    url: https://deepmind.google/blog/rss.xml
  - name: Google AI
    url: https://blog.google/technology/ai/rss/
  - name: Hugging Face
    url: https://huggingface.co/blog/feed.xml
  # Anthropic has no official feed; this one is community-maintained.
  - name: Anthropic
    url: https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml
  - name: Simon Willison
    url: https://simonwillison.net/atom/everything/
  - name: Import AI
    url: https://importai.substack.com/feed
  - name: The Batch
    url: https://www.deeplearning.ai/the-batch/feed/
  - name: MIT Technology Review
    url: https://www.technologyreview.com/topic/artificial-intelligence/feed

# AI coding tools: every notable release is covered, grouped by tool.
devtools:
  - name: Claude Code
    url: https://github.com/anthropics/claude-code/releases.atom
  - name: OpenAI Codex
    url: https://github.com/openai/codex/releases.atom
  - name: Gemini CLI
    url: https://github.com/google-gemini/gemini-cli/releases.atom
  - name: GitHub Changelog
    url: https://github.blog/changelog/feed/
  - name: Cursor
    url: https://cursor.com/changelog/rss.xml
```

`config/keywords.yaml`:
```yaml
# Paper pre-filter: weight added when a term appears in the abstract,
# multiplied by title_weight when it appears in the title. Plurals match too.
papers:
  title_weight: 2.0
  positive:
    # Agents
    agent: 3
    agentic: 3
    multi-agent: 3
    tool use: 2
    tool calling: 2
    planning: 1
    # Inference and deployment
    inference: 2
    serving: 3
    speculative decoding: 3
    quantization: 3
    kv cache: 3
    kv-cache: 3
    latency: 1
    throughput: 1
    distillation: 1
    deployment: 2
    on-device: 1
    # RAG and retrieval
    retrieval-augmented: 3
    rag: 3
    retrieval: 2
    reranking: 2
    embedding: 1
    # Evaluation
    evaluation: 2
    benchmark: 1
    contamination: 3
    llm-as-a-judge: 3
    reward model: 2
    # LLMs and general ML
    large language model: 1
    llm: 1
    language model: 1
    in-context learning: 2
    scaling law: 3
    interpretability: 2
    reinforcement learning: 1
    fine-tuning: 1
    # ML-related statistics
    uncertainty quantification: 3
    conformal prediction: 3
    calibration: 2
    bayesian: 2
    causal inference: 3
    causal: 1
    hypothesis testing: 2
  negative:
    medical imaging: 3
    remote sensing: 3
    radiology: 2
    autonomous driving: 2
    point cloud: 2
    hyperspectral: 3

# Trending repos: kept when name/description matches an include term;
# dropped when the repo name contains an exclude substring.
repos:
  include: [llm, agent, agentic, rag, inference, mcp, machine learning, deep learning,
            transformer, embedding, claude, gpt, language model, diffusion, ml, ai]
  exclude: [awesome, prompts, tutorial, course, interview, roadmap, cheatsheet]
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit/test_config.py -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/config.py config tests/unit/test_config.py
git commit -m "feat: add typed configuration with default settings, sources and keywords

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Keyword pre-filter for papers

**Files:**
- Create: `src/weekly_ai_newsletter/services/__init__.py` (empty), `services/text.py`, `services/keyword_filter.py`, `tests/unit/test_keyword_filter.py`

**Interfaces:**
- Consumes: `Paper`, `PaperKeywords`.
- Produces: `keyword_pattern(term: str) -> re.Pattern[str]` (case-insensitive, word-boundary, optional plural `s`/`es`), `truncate(text: str, limit: int) -> str`, `KeywordFilter(keywords: PaperKeywords)`, `.score(paper) -> float`, `.top(papers: Iterable[Paper], limit: int) -> list[Paper]` (only score > 0, sorted by score desc then arxiv_id).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_keyword_filter.py`:
```python
from tests.factories import make_paper
from weekly_ai_newsletter.config import PaperKeywords
from weekly_ai_newsletter.services.keyword_filter import KeywordFilter
from weekly_ai_newsletter.services.text import keyword_pattern, truncate

KEYWORDS = PaperKeywords(
    title_weight=2.0,
    positive={"agent": 3, "rag": 3, "quantization": 2},
    negative={"medical imaging": 5},
)


def test_pattern_matches_plurals_and_ignores_case_but_respects_word_boundaries() -> None:
    pattern = keyword_pattern("agent")
    assert pattern.search("LLM Agents in the wild")
    assert not pattern.search("reagent chemistry")
    assert not keyword_pattern("rag").search("ragged arrays")


def test_title_matches_weigh_more_than_abstract_matches() -> None:
    keyword_filter = KeywordFilter(KEYWORDS)
    in_title = make_paper(title="Agents for science", abstract="We study things.")
    in_abstract = make_paper(title="A study", abstract="We build an agent.")
    assert keyword_filter.score(in_title) == 6.0
    assert keyword_filter.score(in_abstract) == 3.0


def test_negative_terms_subtract() -> None:
    paper = make_paper(title="RAG for medical imaging", abstract="")
    assert KeywordFilter(KEYWORDS).score(paper) == 2 * 3 - 2 * 5


def test_top_keeps_positive_scores_sorted_and_limited() -> None:
    papers = [
        make_paper("2610.00003", title="Quantization", abstract=""),
        make_paper("2610.00001", title="Agent RAG", abstract=""),
        make_paper("2610.00002", title="Unrelated topic", abstract=""),
        make_paper("2610.00004", title="Agent", abstract=""),
    ]
    top = KeywordFilter(KEYWORDS).top(papers, limit=2)
    assert [p.arxiv_id for p in top] == ["2610.00001", "2610.00004"]


def test_truncate_adds_ellipsis_only_when_needed() -> None:
    assert truncate("short", 10) == "short"
    assert truncate("abcdefghijkl", 5) == "abcd…"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_keyword_filter.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/services/text.py`:
```python
import re


def keyword_pattern(term: str) -> re.Pattern[str]:
    """Case-insensitive whole-word match for `term`, tolerating a plural suffix."""
    return re.compile(rf"\b{re.escape(term)}(?:s|es)?\b", re.IGNORECASE)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
```

`src/weekly_ai_newsletter/services/keyword_filter.py`:
```python
from __future__ import annotations

from collections.abc import Iterable

from weekly_ai_newsletter.config import PaperKeywords
from weekly_ai_newsletter.domain.models import Paper
from weekly_ai_newsletter.services.text import keyword_pattern


class KeywordFilter:
    """Cheap, deterministic relevance pre-filter run before any LLM call."""

    def __init__(self, keywords: PaperKeywords) -> None:
        self._title_weight = keywords.title_weight
        self._terms = [(keyword_pattern(term), weight) for term, weight in keywords.positive.items()]
        self._terms += [
            (keyword_pattern(term), -weight) for term, weight in keywords.negative.items()
        ]

    def score(self, paper: Paper) -> float:
        total = 0.0
        for pattern, weight in self._terms:
            if pattern.search(paper.title):
                total += weight * self._title_weight
            if pattern.search(paper.abstract):
                total += weight
        return total

    def top(self, papers: Iterable[Paper], limit: int) -> list[Paper]:
        scored = [(self.score(paper), paper) for paper in papers]
        relevant = [(score, paper) for score, paper in scored if score > 0]
        relevant.sort(key=lambda pair: (-pair[0], pair[1].arxiv_id))
        return [paper for _, paper in relevant[:limit]]
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/unit/test_keyword_filter.py -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/services tests/unit/test_keyword_filter.py
git commit -m "feat: add weighted keyword pre-filter for papers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Paper selection rules

**Files:**
- Create: `src/weekly_ai_newsletter/services/paper_selection.py`, `tests/unit/test_paper_selection.py`

**Interfaces:**
- Consumes: `ScoredPaper`, `PaperScore.total`.
- Produces: `SelectionRules(min_total: int, min_novelty: int, max_selected: int)`, `select_papers(scored: Iterable[ScoredPaper], rules: SelectionRules) -> list[ScoredPaper]`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_paper_selection.py`:
```python
from tests.factories import make_paper, make_score
from weekly_ai_newsletter.domain.models import ScoredPaper
from weekly_ai_newsletter.services.paper_selection import SelectionRules, select_papers

RULES = SelectionRules(min_total=45, min_novelty=6, max_selected=3)


def scored(arxiv_id: str, **scores: int | bool) -> ScoredPaper:
    return ScoredPaper(make_paper(arxiv_id), make_score(arxiv_id, **scores))  # type: ignore[arg-type]


def test_drops_incremental_low_novelty_and_low_total() -> None:
    papers = [
        scored("a", relevance=10, novelty=9, is_incremental=True),
        scored("b", relevance=10, novelty=5, evidence=10, depth=10, practical_utility=10),
        scored("c", relevance=5, novelty=6, evidence=5, depth=5, practical_utility=5),  # 37
        scored("d", relevance=8, novelty=8),  # 2*8 + 2*8 + 21 = 53
    ]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["d"]


def test_keeps_at_most_max_selected_sorted_by_total() -> None:
    papers = [scored(str(i), relevance=6 + i, novelty=7) for i in range(5)]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["4", "3", "2"]


def test_ties_broken_by_relevance_plus_novelty_then_id() -> None:
    papers = [
        scored("z", relevance=7, novelty=7, evidence=9),  # total 46, r+n 14
        scored("y", relevance=8, novelty=7, evidence=7),  # total 46, r+n 15
        scored("x", relevance=7, novelty=7, evidence=9),  # total 46, r+n 14
    ]
    assert [p.paper.arxiv_id for p in select_papers(papers, RULES)] == ["y", "x", "z"]


def test_returns_empty_when_nothing_qualifies() -> None:
    assert select_papers([scored("a", relevance=3, novelty=3)], RULES) == []
```

Note the `# type: ignore[arg-type]` on the helper: `**scores` is `int | bool` and `make_score` has separate keyword types. If mypy reports the ignore as unused, remove it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_paper_selection.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/services/paper_selection.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from weekly_ai_newsletter.domain.models import ScoredPaper


@dataclass(frozen=True)
class SelectionRules:
    min_total: int
    min_novelty: int
    max_selected: int


def select_papers(scored: Iterable[ScoredPaper], rules: SelectionRules) -> list[ScoredPaper]:
    """Keep the best papers that are novel enough; an empty result is valid."""
    eligible = [
        candidate
        for candidate in scored
        if not candidate.score.is_incremental
        and candidate.score.novelty >= rules.min_novelty
        and candidate.score.total >= rules.min_total
    ]
    eligible.sort(
        key=lambda c: (
            -c.score.total,
            -(c.score.relevance + c.score.novelty),
            c.paper.arxiv_id,
        )
    )
    return eligible[: rules.max_selected]
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/unit/test_paper_selection.py -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/services/paper_selection.py tests/unit/test_paper_selection.py
git commit -m "feat: add deterministic paper selection rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Prompts, paper scorer and paper writer

**Files:**
- Create: `src/weekly_ai_newsletter/prompts/__init__.py`, `prompts/score_papers.md.j2`, `prompts/write_papers.md.j2`, `services/paper_scorer.py`, `services/paper_writer.py`, `tests/fakes.py`, `tests/unit/test_paper_scorer.py`, `tests/unit/test_paper_writer.py`

**Interfaces:**
- Consumes: `LLMClient` port, `Paper`, `PaperScore`, `ScoredPaper`, `SelectedPaper`, `LLMOutputError`, `Language`.
- Produces:
  - `LANGUAGE_NAMES: dict[str, str]` (`{"fr": "French", "en": "English"}`), `render_prompt(name: str, **context: object) -> str`
  - `PaperScoreBatch(scores: list[PaperScore])`, `PaperScorer(llm, *, batch_size: int)`, `.score(papers: Sequence[Paper]) -> list[ScoredPaper]` (skips batches raising `LLMOutputError`; ignores unknown/duplicate IDs)
  - `PaperWriteup(arxiv_id, summary, why_selected)`, `PaperWriteupBatch(writeups)`, `PaperWriter(llm, *, language: str)`, `.write(selected: Sequence[ScoredPaper]) -> list[SelectedPaper]` (raises `LLMOutputError` if a write-up is missing)
  - `tests/fakes.py`: `FakeLLM(responses: Mapping[type[BaseModel], Handler])` where `Handler = Callable[[str], BaseModel] | BaseModel | Exception`; attribute `calls: list[tuple[str, str, type[BaseModel]]]` (system, prompt, model)

- [ ] **Step 1: Write the prompt loader and prompts**

`src/weekly_ai_newsletter/prompts/__init__.py`:
```python
"""System prompts, kept as templates so they can be reviewed and versioned like code."""

from jinja2 import Environment, PackageLoader, StrictUndefined

LANGUAGE_NAMES = {"fr": "French", "en": "English"}

_env = Environment(
    loader=PackageLoader("weekly_ai_newsletter", "prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_prompt(name: str, **context: object) -> str:
    return _env.get_template(name).render(**context)
```

`src/weekly_ai_newsletter/prompts/score_papers.md.j2`:
```
You are a demanding research curator for a weekly AI newsletter. The reader is a
machine-learning practitioner who wants papers that genuinely teach something, even
when they are highly technical.

Reader interests:
- LLM agents: planning, tool use, memory, multi-agent systems, agent evaluation
- Inference and serving: quantization, speculative decoding, KV cache, batching, efficient architectures for deployment
- Deployment of ML systems: reliability, monitoring, cost
- Retrieval-augmented generation and retrieval
- Model evaluation: benchmark design, contamination, LLM-as-a-judge, statistical rigor of evaluations
- Machine learning in general, and ML-related statistics: uncertainty quantification, Bayesian methods, conformal prediction, causal inference, calibration

You receive a JSON list of papers (arxiv_id, title, abstract). Score EVERY paper on
five criteria, each an integer from 1 to 10:

- relevance: fit with the reader's interests. 9-10 core topic; 5 adjacent; 1-2 unrelated.
- novelty: a genuinely new idea, finding or perspective? 9-10 a method or insight others
  will build on, or a surprising empirical finding; 5 a sensible combination of known
  ideas; 1-3 a small benchmark gain, a minor architecture variant, or an existing method
  under a new name.
- evidence: strength of the support described. 9-10 rigorous experiments with ablations
  across settings, or proofs; 5 a few experiments; 1-3 claims without clear evidence.
- depth: how much the reader learns about why things work. 9-10 mechanistic
  understanding, theory, careful analysis; 1-3 superficial.
- practical_utility: can a practitioner apply it? 9-10 directly usable technique, tool
  or guideline; 1-3 no practical consequence.

Set is_incremental to true when the main contribution is a small benchmark improvement,
a minor architectural variant, or a renamed existing method.

A highly technical paper that teaches something important beats an accessible but
incremental one. Be strict: most papers should score between 3 and 6 on novelty.
Judge only from the title and abstract; never invent results.

Write rationale as one or two short English sentences justifying the scores.
Return exactly one score object per input paper, using the exact arxiv_id given.
```

`src/weekly_ai_newsletter/prompts/write_papers.md.j2`:
```
You write the research section of a weekly AI newsletter for a machine-learning
practitioner. You receive a JSON list of selected papers with their abstracts, scores
and the curator's rationale.

For each paper, write in {{ language }}:
- summary: 4 to 6 sentences explaining the problem, the key idea and the main result,
  precise and technical, without hype. Keep standard English technical terms when they
  are the usual vocabulary (e.g. "RAG", "KV cache").
- why_selected: 2 or 3 sentences on what the reader learns from this paper and why it
  matters in practice.

Only use information present in the input. Return one write-up per paper, using the
exact arxiv_id given.
```

- [ ] **Step 2: Write the fake LLM**

`tests/fakes.py`:
```python
from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel

Handler = Callable[[str], BaseModel] | BaseModel | Exception


class FakeLLM:
    """LLMClient double: answers by output model type, records every call."""

    def __init__(self, responses: Mapping[type[BaseModel], Handler]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        self.calls.append((system, prompt, output_model))
        handler = self._responses[output_model]
        if isinstance(handler, Exception):
            raise handler
        result = handler if isinstance(handler, BaseModel) else handler(prompt)
        assert isinstance(result, output_model)
        return result
```

- [ ] **Step 3: Write the failing tests**

`tests/unit/test_paper_scorer.py`:
```python
import json

from pydantic import BaseModel

from tests.factories import make_paper, make_score
from tests.fakes import FakeLLM
from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.services.paper_scorer import PaperScoreBatch, PaperScorer


def score_every_paper(prompt: str) -> BaseModel:
    ids = [item["arxiv_id"] for item in json.loads(prompt)]
    return PaperScoreBatch(scores=[make_score(arxiv_id) for arxiv_id in ids])


def test_scores_papers_in_batches() -> None:
    llm = FakeLLM({PaperScoreBatch: score_every_paper})
    papers = [make_paper(f"2610.0000{i}") for i in range(5)]
    result = PaperScorer(llm, batch_size=2).score(papers)
    assert len(llm.calls) == 3
    assert [r.paper.arxiv_id for r in result] == [p.arxiv_id for p in papers]
    assert "Score EVERY paper" in llm.calls[0][0]


def test_ignores_unknown_and_duplicate_ids() -> None:
    def answer(prompt: str) -> BaseModel:
        return PaperScoreBatch(
            scores=[make_score("2610.00001"), make_score("2610.00001"), make_score("9999.99999")]
        )

    result = PaperScorer(FakeLLM({PaperScoreBatch: answer}), batch_size=10).score(
        [make_paper("2610.00001"), make_paper("2610.00002")]
    )
    assert [r.paper.arxiv_id for r in result] == ["2610.00001"]


def test_skips_a_batch_with_invalid_output() -> None:
    calls = 0

    def flaky(prompt: str) -> BaseModel:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LLMOutputError("bad json")
        return score_every_paper(prompt)

    papers = [make_paper("2610.00001"), make_paper("2610.00002")]
    result = PaperScorer(FakeLLM({PaperScoreBatch: flaky}), batch_size=1).score(papers)
    assert [r.paper.arxiv_id for r in result] == ["2610.00002"]
```

The `flaky` handler raises from inside a callable; `FakeLLM` propagates that exception naturally, which is what the scorer must catch.

`tests/unit/test_paper_writer.py`:
```python
import pytest

from tests.factories import make_paper, make_score
from tests.fakes import FakeLLM
from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import ScoredPaper
from weekly_ai_newsletter.services.paper_writer import (
    PaperWriteup,
    PaperWriteupBatch,
    PaperWriter,
)

SELECTED = [ScoredPaper(make_paper("2610.00001", title="Agents"), make_score("2610.00001"))]


def test_writes_summary_and_reason_in_configured_language() -> None:
    llm = FakeLLM(
        {
            PaperWriteupBatch: PaperWriteupBatch(
                writeups=[PaperWriteup(arxiv_id="2610.00001", summary="Résumé.", why_selected="Car.")]
            )
        }
    )
    [paper] = PaperWriter(llm, language="fr").write(SELECTED)
    assert (paper.summary, paper.why_selected) == ("Résumé.", "Car.")
    assert paper.paper.title == "Agents"
    assert "French" in llm.calls[0][0]


def test_missing_writeup_is_an_error() -> None:
    llm = FakeLLM({PaperWriteupBatch: PaperWriteupBatch(writeups=[])})
    with pytest.raises(LLMOutputError, match="2610.00001"):
        PaperWriter(llm, language="en").write(SELECTED)


def test_no_call_when_nothing_selected() -> None:
    llm = FakeLLM({})
    assert PaperWriter(llm, language="en").write([]) == []
    assert llm.calls == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_paper_scorer.py tests/unit/test_paper_writer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 5: Implement the scorer and writer**

`src/weekly_ai_newsletter/services/paper_scorer.py`:
```python
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from itertools import batched

from pydantic import BaseModel

from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import Paper, PaperScore, ScoredPaper
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import render_prompt

logger = logging.getLogger(__name__)


class PaperScoreBatch(BaseModel):
    scores: list[PaperScore]


class PaperScorer:
    """Asks the LLM for per-criterion scores; aggregation happens in PaperScore.total."""

    def __init__(self, llm: LLMClient, *, batch_size: int) -> None:
        self._llm = llm
        self._batch_size = batch_size

    def score(self, papers: Sequence[Paper]) -> list[ScoredPaper]:
        system = render_prompt("score_papers.md.j2")
        results: list[ScoredPaper] = []
        for batch in batched(papers, self._batch_size):
            prompt = json.dumps(
                [{"arxiv_id": p.arxiv_id, "title": p.title, "abstract": p.abstract} for p in batch],
                ensure_ascii=False,
                indent=2,
            )
            try:
                answer = self._llm.structured(
                    system=system, prompt=prompt, output_model=PaperScoreBatch
                )
            except LLMOutputError:
                logger.warning("Skipping a batch of %d papers: invalid LLM output", len(batch))
                continue
            pending = {paper.arxiv_id: paper for paper in batch}
            for score in answer.scores:
                paper = pending.pop(score.arxiv_id, None)
                if paper is not None:
                    results.append(ScoredPaper(paper=paper, score=score))
        return results
```

`src/weekly_ai_newsletter/services/paper_writer.py`:
```python
from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.errors import LLMOutputError
from weekly_ai_newsletter.domain.models import ScoredPaper, SelectedPaper
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt


class PaperWriteup(BaseModel):
    arxiv_id: str
    summary: str
    why_selected: str


class PaperWriteupBatch(BaseModel):
    writeups: list[PaperWriteup]


class PaperWriter:
    def __init__(self, llm: LLMClient, *, language: str) -> None:
        self._llm = llm
        self._language = language

    def write(self, selected: Sequence[ScoredPaper]) -> list[SelectedPaper]:
        if not selected:
            return []
        system = render_prompt("write_papers.md.j2", language=LANGUAGE_NAMES[self._language])
        prompt = json.dumps(
            [
                {
                    "arxiv_id": c.paper.arxiv_id,
                    "title": c.paper.title,
                    "abstract": c.paper.abstract,
                    "scores": c.score.model_dump(exclude={"arxiv_id", "rationale"}),
                    "curator_rationale": c.score.rationale,
                }
                for c in selected
            ],
            ensure_ascii=False,
            indent=2,
        )
        answer = self._llm.structured(system=system, prompt=prompt, output_model=PaperWriteupBatch)
        writeups = {w.arxiv_id: w for w in answer.writeups}
        missing = [c.paper.arxiv_id for c in selected if c.paper.arxiv_id not in writeups]
        if missing:
            raise LLMOutputError(f"missing write-ups for {', '.join(missing)}")
        return [
            SelectedPaper(
                paper=c.paper,
                score=c.score,
                summary=writeups[c.paper.arxiv_id].summary,
                why_selected=writeups[c.paper.arxiv_id].why_selected,
            )
            for c in selected
        ]
```

- [ ] **Step 6: Run tests and checks**

Run: `uv run pytest tests/unit -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/weekly_ai_newsletter/prompts src/weekly_ai_newsletter/services tests/fakes.py tests/unit
git commit -m "feat: score papers and write summaries with the LLM

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: News and dev-tools curators

**Files:**
- Create: `prompts/curate_news.md.j2`, `prompts/curate_devtools.md.j2`, `services/news_curator.py`, `services/devtools_curator.py`, `tests/unit/test_news_curator.py`, `tests/unit/test_devtools_curator.py`

**Interfaces:**
- Consumes: `FeedItem`, `NewsItem`, `DevToolChange`, `DevToolGroup`, `render_prompt`, `LANGUAGE_NAMES`, `truncate`, `FakeLLM`.
- Produces:
  - `NewsPick(index: int, summary: str)`, `NewsSelection(picks: list[NewsPick])`, `NewsCurator(llm, *, language, max_items)`, `.curate(items: Sequence[FeedItem]) -> list[NewsItem]`
  - `ChangePick(index: int, summary: str)`, `ToolGroup(tool: str, changes: list[ChangePick])`, `DevToolsSelection(groups: list[ToolGroup])`, `DevToolsCurator(llm, *, language)`, `.curate(items: Sequence[FeedItem]) -> list[DevToolGroup]`
  - Both: indices out of range or repeated are ignored; empty input → `[]` without an LLM call.

- [ ] **Step 1: Write the prompts**

`src/weekly_ai_newsletter/prompts/curate_news.md.j2`:
```
You curate the "AI news" section of a weekly newsletter for a machine-learning
practitioner. You receive a JSON list of this week's articles (index, source, title,
summary).

Pick at most {{ max_items }} items that matter most: major model or product releases,
important research results, significant open-source releases, policy or industry
events with real consequences for practitioners. When several articles cover the same
story, pick the single most informative one. Skip opinion pieces, minor updates and
marketing.

For each pick, return its index and a summary of 2 to 3 sentences in {{ language }}
stating what happened and why it matters. Order picks from most to least important.
Only use information present in the input.
```

`src/weekly_ai_newsletter/prompts/curate_devtools.md.j2`:
```
You curate the "AI dev tools" section of a weekly newsletter. The reader uses AI coding
tools daily and does not want to miss any notable change. You receive a JSON list of
this week's release notes and changelog entries (index, source, title, content).

Group the notable changes by tool, using the product name as the group name (for
example "Claude Code", "OpenAI Codex", "Cursor", "GitHub Copilot", "Gemini CLI").
A notable change is a new feature, a behaviour change, a new model or integration, or
a deprecation. Ignore releases that only contain bug fixes, dependency bumps or
internal maintenance. Entries from a general changelog that are not about an AI coding
tool must be ignored.

For each kept entry, return its index and a summary of 1 to 2 sentences in
{{ language }} listing the notable changes concretely. Only use information present in
the input.
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_news_curator.py`:
```python
from tests.factories import make_feed_item
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.news_curator import NewsCurator, NewsPick, NewsSelection

ITEMS = [
    make_feed_item("https://a.example/1", title="Model X released", source="Lab A"),
    make_feed_item("https://b.example/2", title="Minor update", source="Lab B"),
]


def test_maps_picks_back_to_source_urls() -> None:
    llm = FakeLLM(
        {NewsSelection: NewsSelection(picks=[NewsPick(index=0, summary="Big release.")])}
    )
    [item] = NewsCurator(llm, language="fr", max_items=6).curate(ITEMS)
    assert (item.title, item.url, item.source, item.summary) == (
        "Model X released",
        "https://a.example/1",
        "Lab A",
        "Big release.",
    )
    assert "French" in llm.calls[0][0] and "at most 6" in llm.calls[0][0]


def test_ignores_invalid_and_repeated_indices_and_caps_count() -> None:
    picks = [NewsPick(index=i, summary="s") for i in (5, 1, 1, -1, 0)]
    llm = FakeLLM({NewsSelection: NewsSelection(picks=picks)})
    result = NewsCurator(llm, language="en", max_items=1).curate(ITEMS)
    assert [item.url for item in result] == ["https://b.example/2"]


def test_empty_input_skips_llm() -> None:
    llm = FakeLLM({})
    assert NewsCurator(llm, language="en", max_items=6).curate([]) == []
    assert llm.calls == []
```

`tests/unit/test_devtools_curator.py`:
```python
from tests.factories import make_feed_item
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.devtools_curator import (
    ChangePick,
    DevToolsCurator,
    DevToolsSelection,
    ToolGroup,
)

ITEMS = [
    make_feed_item("https://gh.example/cc/v2.1.0", title="v2.1.0", source="Claude Code"),
    make_feed_item("https://gh.example/cc/v2.1.1", title="v2.1.1", source="Claude Code"),
    make_feed_item("https://gh.example/codex/v0.9", title="0.9", source="OpenAI Codex"),
]


def test_groups_changes_by_tool_with_source_urls() -> None:
    selection = DevToolsSelection(
        groups=[
            ToolGroup(tool="Claude Code", changes=[ChangePick(index=0, summary="Hooks.")]),
            ToolGroup(tool="OpenAI Codex", changes=[ChangePick(index=2, summary="Sandbox.")]),
        ]
    )
    groups = DevToolsCurator(FakeLLM({DevToolsSelection: selection}), language="en").curate(ITEMS)
    assert [g.tool for g in groups] == ["Claude Code", "OpenAI Codex"]
    assert groups[0].changes[0].url == "https://gh.example/cc/v2.1.0"
    assert groups[0].changes[0].title == "v2.1.0"


def test_drops_groups_without_valid_changes() -> None:
    selection = DevToolsSelection(
        groups=[ToolGroup(tool="Ghost", changes=[ChangePick(index=42, summary="x")])]
    )
    assert DevToolsCurator(FakeLLM({DevToolsSelection: selection}), language="en").curate(ITEMS) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_news_curator.py tests/unit/test_devtools_curator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`src/weekly_ai_newsletter/services/news_curator.py`:
```python
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
```

`src/weekly_ai_newsletter/services/devtools_curator.py`:
```python
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
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/prompts src/weekly_ai_newsletter/services tests/unit
git commit -m "feat: curate AI news and dev-tool releases with the LLM

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Repo rule filter and repo curator

**Files:**
- Create: `prompts/curate_repos.md.j2`, `services/repo_filter.py`, `services/repo_curator.py`, `tests/unit/test_repo_filter.py`, `tests/unit/test_repo_curator.py`

**Interfaces:**
- Consumes: `Repo`, `CuratedRepo`, `RepoKeywords`, `keyword_pattern`.
- Produces: `RepoRuleFilter(keywords: RepoKeywords)`, `.keep(repo) -> bool`, `.apply(repos: Iterable[Repo]) -> list[Repo]`; `RepoVerdict(full_name, keep, why_interesting)`, `RepoVerdicts(verdicts)`, `RepoCurator(llm, *, language, max_items)`, `.curate(repos: Sequence[Repo]) -> list[CuratedRepo]` (sorted by `stars_this_week` desc, then `full_name`).

- [ ] **Step 1: Write the prompt**

`src/weekly_ai_newsletter/prompts/curate_repos.md.j2`:
```
You review GitHub repositories trending this week for the "GitHub" section of an AI
newsletter read by a machine-learning practitioner. You receive a JSON list
(full_name, description, language, stars_this_week).

For each repository decide keep (true/false). Keep only genuinely useful AI/ML software:
libraries, frameworks, tools, models, inference engines, agent or RAG infrastructure.
Reject curated lists, prompt collections, tutorials and courses, clones of existing
apps, crypto projects, and repositories whose link to AI/ML is superficial.

For kept repositories, write why_interesting as one sentence in {{ language }}
explaining what it does and why a practitioner would care. For rejected ones,
why_interesting may be empty. Return one verdict per input repository, using the
exact full_name given. Only use information present in the input.
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_repo_filter.py`:
```python
from tests.factories import make_repo
from weekly_ai_newsletter.config import RepoKeywords
from weekly_ai_newsletter.services.repo_filter import RepoRuleFilter

FILTER = RepoRuleFilter(RepoKeywords(include=["llm", "agent", "ai"], exclude=["awesome", "prompts"]))


def test_keeps_ai_repos_matching_name_or_description() -> None:
    assert FILTER.keep(make_repo("acme/agent-kit", description="Toolkit"))
    assert FILTER.keep(make_repo("acme/toolkit", description="Serve LLMs fast"))


def test_drops_lists_prompt_collections_and_repos_without_code() -> None:
    assert not FILTER.keep(make_repo("someone/awesome-llm"))
    assert not FILTER.keep(make_repo("someone/system-prompts", description="LLM prompts"))
    assert not FILTER.keep(make_repo("someone/llm-notes", language=None))


def test_drops_unrelated_repos_and_avoids_substring_false_positives() -> None:
    assert not FILTER.keep(make_repo("acme/mail-client", description="Email for humans"))


def test_apply_filters_a_list() -> None:
    repos = [make_repo("acme/agent-kit"), make_repo("acme/mail-client", description="Email")]
    assert [r.full_name for r in FILTER.apply(repos)] == ["acme/agent-kit"]
```

`tests/unit/test_repo_curator.py`:
```python
from tests.factories import make_repo
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.repo_curator import RepoCurator, RepoVerdict, RepoVerdicts

REPOS = [
    make_repo("a/slow", stars_this_week=100),
    make_repo("b/fast", stars_this_week=900),
    make_repo("c/hype", stars_this_week=5000),
]


def test_keeps_validated_repos_ranked_by_stars_gained() -> None:
    verdicts = RepoVerdicts(
        verdicts=[
            RepoVerdict(full_name="a/slow", keep=True, why_interesting="Useful."),
            RepoVerdict(full_name="b/fast", keep=True, why_interesting="Great."),
            RepoVerdict(full_name="c/hype", keep=False, why_interesting=""),
            RepoVerdict(full_name="z/invented", keep=True, why_interesting="?"),
        ]
    )
    curated = RepoCurator(FakeLLM({RepoVerdicts: verdicts}), language="en", max_items=5).curate(REPOS)
    assert [c.repo.full_name for c in curated] == ["b/fast", "a/slow"]
    assert curated[0].why_interesting == "Great."


def test_caps_number_of_repos() -> None:
    verdicts = RepoVerdicts(
        verdicts=[RepoVerdict(full_name=r.full_name, keep=True, why_interesting="x") for r in REPOS]
    )
    curated = RepoCurator(FakeLLM({RepoVerdicts: verdicts}), language="en", max_items=2).curate(REPOS)
    assert [c.repo.full_name for c in curated] == ["c/hype", "b/fast"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_repo_filter.py tests/unit/test_repo_curator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`src/weekly_ai_newsletter/services/repo_filter.py`:
```python
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
```

`src/weekly_ai_newsletter/services/repo_curator.py`:
```python
from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from weekly_ai_newsletter.domain.models import CuratedRepo, Repo
from weekly_ai_newsletter.ports import LLMClient
from weekly_ai_newsletter.prompts import LANGUAGE_NAMES, render_prompt


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
        pending = {repo.full_name: repo for repo in repos}
        kept: list[CuratedRepo] = []
        for verdict in answer.verdicts:
            repo = pending.pop(verdict.full_name, None)
            if repo is not None and verdict.keep:
                kept.append(CuratedRepo(repo=repo, why_interesting=verdict.why_interesting))
        kept.sort(key=lambda c: (-c.repo.stars_this_week, c.repo.full_name))
        return kept[: self._max_items]
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/prompts src/weekly_ai_newsletter/services tests/unit
git commit -m "feat: filter and curate trending GitHub repositories

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Deduplication and JSON history store

**Files:**
- Create: `services/dedup.py`, `src/weekly_ai_newsletter/adapters/__init__.py` (empty), `adapters/json_history.py`, `state/.gitkeep`, `archive/.gitkeep`, `tests/unit/test_dedup.py`, `tests/adapters/__init__.py` (empty), `tests/adapters/test_json_history.py`

**Interfaces:**
- Consumes: `History`, `HistoryKind`.
- Produces: `unique_by(items: Iterable[T], key: Callable[[T], str]) -> list[T]` (first occurrence wins, order kept); `drop_sent(items: Iterable[T], *, key: Callable[[T], str], history: History, kind: HistoryKind, since: date | None = None) -> list[T]`; `JsonHistoryStore(path: Path)` implementing `HistoryStore`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_dedup.py`:
```python
from datetime import date

from tests.factories import make_feed_item, make_repo
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.services.dedup import drop_sent, unique_by


def test_unique_by_keeps_first_occurrence_in_order() -> None:
    items = [make_feed_item("u1", source="A"), make_feed_item("u2"), make_feed_item("u1", source="B")]
    assert [(i.url, i.source) for i in unique_by(items, key=lambda i: i.url)] == [
        ("u1", "A"),
        ("u2", "Example"),
    ]


def test_drop_sent_removes_items_already_in_history() -> None:
    history = History()
    history.record(HistoryKind.NEWS, ["u1"], date(2026, 10, 28))
    items = [make_feed_item("u1"), make_feed_item("u2")]
    fresh = drop_sent(items, key=lambda i: i.url, history=history, kind=HistoryKind.NEWS)
    assert [i.url for i in fresh] == ["u2"]


def test_drop_sent_with_cutoff_lets_old_entries_come_back() -> None:
    history = History()
    history.record(HistoryKind.REPO, ["acme/old"], date(2026, 8, 1))
    history.record(HistoryKind.REPO, ["acme/recent"], date(2026, 10, 28))
    repos = [make_repo("acme/old"), make_repo("acme/recent")]
    fresh = drop_sent(
        repos,
        key=lambda r: r.full_name,
        history=history,
        kind=HistoryKind.REPO,
        since=date(2026, 9, 9),
    )
    assert [r.full_name for r in fresh] == ["acme/old"]
```

`tests/adapters/test_json_history.py`:
```python
from datetime import date
from pathlib import Path

from weekly_ai_newsletter.adapters.json_history import JsonHistoryStore
from weekly_ai_newsletter.domain.history import History, HistoryKind


def test_missing_file_loads_empty_history(tmp_path: Path) -> None:
    assert JsonHistoryStore(tmp_path / "nope.json").load().entries == {}


def test_round_trip_is_stable_and_human_readable(tmp_path: Path) -> None:
    path = tmp_path / "state" / "history.json"
    history = History()
    history.record(HistoryKind.PAPER, ["2610.00002", "2610.00001"], date(2026, 11, 4))
    store = JsonHistoryStore(path)
    store.save(history)
    assert store.load() == history
    text = path.read_text(encoding="utf-8")
    assert text.index("2610.00001") < text.index("2610.00002")
    assert '"2026-11-04"' in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_dedup.py tests/adapters/test_json_history.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/services/dedup.py`:
```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from weekly_ai_newsletter.domain.history import History, HistoryKind


def unique_by[T](items: Iterable[T], key: Callable[[T], str]) -> list[T]:
    seen: set[str] = set()
    unique: list[T] = []
    for item in items:
        if key(item) not in seen:
            seen.add(key(item))
            unique.append(item)
    return unique


def drop_sent[T](
    items: Iterable[T],
    *,
    key: Callable[[T], str],
    history: History,
    kind: HistoryKind,
    since: date | None = None,
) -> list[T]:
    """Remove items already sent (only those sent on/after `since`, when given)."""
    return [item for item in items if not history.was_sent(kind, key(item), on_or_after=since)]
```

`src/weekly_ai_newsletter/adapters/json_history.py`:
```python
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from weekly_ai_newsletter.domain.history import History, HistoryKind


class JsonHistoryStore:
    """History persisted as a sorted, diff-friendly JSON file committed to the repo."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> History:
        if not self._path.exists():
            return History()
        raw: dict[str, dict[str, str]] = json.loads(self._path.read_text(encoding="utf-8"))
        return History(
            entries={
                HistoryKind(kind): {key: date.fromisoformat(day) for key, day in bucket.items()}
                for kind, bucket in raw.items()
            }
        )

    def save(self, history: History) -> None:
        data = {
            kind.value: {key: day.isoformat() for key, day in sorted(bucket.items())}
            for kind, bucket in sorted(history.entries.items())
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
```

Create empty `state/.gitkeep` and `archive/.gitkeep`.

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src tests state archive
git commit -m "feat: add history-based deduplication and JSON history store

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: HTTP retry helper and arXiv adapter

**Files:**
- Create: `adapters/http.py`, `adapters/arxiv.py`, `tests/adapters/test_http.py`, `tests/adapters/test_arxiv.py`

**Interfaces:**
- Consumes: `Paper`, `TimeWindow`.
- Produces: `make_http_client(timeout: float = 30.0) -> httpx.Client`; `get_with_retry(client, url, *, params=None, retries=3, backoff=2.0, sleep=time.sleep) -> httpx.Response` (retries on transport errors and 429/500/502/503/504 with delays `backoff * 2**attempt`, raises the last error); `ARXIV_API_URL`; `ArxivPaperSource(client, *, page_size=1000, max_results=20000, delay_seconds=3.0, sleep=time.sleep)` implementing `PaperSource`.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/test_http.py`:
```python
import httpx
import pytest

from weekly_ai_newsletter.adapters.http import get_with_retry


def client_returning(*statuses: int) -> tuple[httpx.Client, list[int]]:
    seen: list[int] = []
    queue = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        status = queue.pop(0)
        seen.append(status)
        return httpx.Response(status, text="ok")

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_retries_retryable_statuses_with_exponential_backoff() -> None:
    client, seen = client_returning(503, 429, 200)
    delays: list[float] = []
    response = get_with_retry(client, "https://x.example", sleep=delays.append)
    assert response.status_code == 200
    assert seen == [503, 429, 200]
    assert delays == [2.0, 4.0]


def test_gives_up_after_retries() -> None:
    client, _ = client_returning(500, 500, 500, 500)
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://x.example", sleep=lambda _: None)


def test_does_not_retry_client_errors() -> None:
    client, seen = client_returning(404)
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(client, "https://x.example", sleep=lambda _: None)
    assert seen == [404]


def test_retries_transport_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectTimeout("slow", request=request)
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert get_with_retry(client, "https://x.example", sleep=lambda _: None).status_code == 200
```

`tests/adapters/test_arxiv.py`:
```python
from datetime import UTC, datetime

import httpx

from weekly_ai_newsletter.adapters.arxiv import ArxivPaperSource
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow(datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC))


def entry(arxiv_id: str, published: str, title: str = "Agents  that\n plan") -> str:
    return f"""
    <entry>
      <id>http://arxiv.org/abs/{arxiv_id}v2</id>
      <published>{published}</published>
      <updated>{published}</updated>
      <title>{title}</title>
      <summary>  We study agents.\n  </summary>
      <author><name>Ada Lovelace</name></author>
      <author><name>Alan Turing</name></author>
      <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
      <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    </entry>"""


def atom(*entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>"
    )


def test_fetches_pages_until_short_page_and_filters_window() -> None:
    pages = {
        "0": atom(entry("2610.00001", "2026-10-28T10:00:00Z"), entry("2610.00002", "2026-10-29T10:00:00Z")),
        "2": atom(entry("2610.00003", "2026-11-02T01:00:00Z")),
    }
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=pages[request.url.params["start"]])

    delays: list[float] = []
    source = ArxivPaperSource(
        httpx.Client(transport=httpx.MockTransport(handler)), page_size=2, sleep=delays.append
    )
    papers = source.fetch(["cs.AI", "cs.LG"], WINDOW)

    assert [p.arxiv_id for p in papers] == ["2610.00001", "2610.00002"]
    assert delays == [3.0]
    query = requests[0].url.params["search_query"]
    assert "cat:cs.AI OR cat:cs.LG" in query
    assert "submittedDate:[202610260000 TO 202611020000]" in query

    paper = papers[0]
    assert paper.title == "Agents that plan"
    assert paper.abstract == "We study agents."
    assert paper.authors == ("Ada Lovelace", "Alan Turing")
    assert paper.categories == ("cs.AI", "cs.LG")
    assert paper.url == "https://arxiv.org/abs/2610.00001"
    assert paper.published == datetime(2026, 10, 28, 10, tzinfo=UTC)


def test_empty_week_returns_no_papers() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=atom())))
    assert ArxivPaperSource(client, sleep=lambda _: None).fetch(["cs.AI"], WINDOW) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_http.py tests/adapters/test_arxiv.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/adapters/http.py`:
```python
from __future__ import annotations

import time
from collections.abc import Callable, Mapping

import httpx

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
USER_AGENT = "weekly-ai-newsletter (+https://github.com/legallclaire/weekly-ai-newsletter)"


def make_http_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, str | int] | None = None,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with exponential backoff on transient failures; other errors raise at once."""
    error: httpx.HTTPError | None = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(backoff * 2 ** (attempt - 1))
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as exc:
            error = exc
            continue
        if response.status_code not in RETRYABLE_STATUSES:
            response.raise_for_status()
            return response
        error = httpx.HTTPStatusError(
            f"retryable status {response.status_code} for {url}",
            request=response.request,
            response=response,
        )
    assert error is not None
    raise error
```

`src/weekly_ai_newsletter/adapters/arxiv.py`:
```python
from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.models import Paper
from weekly_ai_newsletter.domain.window import TimeWindow

ARXIV_API_URL = "https://export.arxiv.org/api/query"
_VERSION_SUFFIX = re.compile(r"v\d+$")


class ArxivPaperSource:
    """Papers submitted in a time window, via the arXiv Atom API (paginated, rate-limited)."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        page_size: int = 1000,
        max_results: int = 20000,
        delay_seconds: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._page_size = page_size
        self._max_results = max_results
        self._delay = delay_seconds
        self._sleep = sleep

    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]:
        query = (
            "(" + " OR ".join(f"cat:{category}" for category in categories) + ")"
            f" AND submittedDate:[{_arxiv_time(window.start)} TO {_arxiv_time(window.end)}]"
        )
        papers: dict[str, Paper] = {}
        for start in range(0, self._max_results, self._page_size):
            if start:
                self._sleep(self._delay)  # arXiv asks for >= 3 s between requests
            response = get_with_retry(
                self._client,
                ARXIV_API_URL,
                params={
                    "search_query": query,
                    "start": start,
                    "max_results": self._page_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                },
                sleep=self._sleep,
            )
            entries = feedparser.parse(response.text).entries
            for entry in entries:
                paper = _to_paper(entry)
                if window.contains(paper.published):
                    papers.setdefault(paper.arxiv_id, paper)
            if len(entries) < self._page_size:
                break
        return list(papers.values())


def _arxiv_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M")


def _clean(text: str) -> str:
    return " ".join(text.split())


def _to_paper(entry: Any) -> Paper:
    arxiv_id = _VERSION_SUFFIX.sub("", entry.id.rsplit("/abs/", 1)[-1])
    return Paper(
        arxiv_id=arxiv_id,
        title=_clean(entry.title),
        abstract=_clean(entry.summary),
        authors=tuple(author.get("name", "") for author in entry.get("authors", [])),
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published=datetime(*entry.published_parsed[:6], tzinfo=UTC),
        categories=tuple(tag.term for tag in entry.get("tags", [])),
    )
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/adapters -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/adapters tests/adapters
git commit -m "feat: add HTTP retry helper and arXiv paper source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: RSS/Atom feed adapter and live feed check

**Files:**
- Create: `adapters/rss.py`, `tests/adapters/test_rss.py`
- Possibly modify: `config/sources.yaml` (after the live check)

**Interfaces:**
- Consumes: `get_with_retry`, `FeedItem`, `TimeWindow`, `SourceError`.
- Produces: `RssFeedSource(client)` implementing `FeedSource`; `html_to_text(html: str) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/test_rss.py`:
```python
from datetime import UTC, datetime

import httpx
import pytest

from weekly_ai_newsletter.adapters.rss import RssFeedSource, html_to_text
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow(datetime(2026, 10, 28, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC))

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Lab blog</title>
<item><title>New  model released</title><link>https://lab.example/new-model</link>
  <description>&lt;p&gt;We release a &lt;b&gt;new&lt;/b&gt; model &amp;amp; tools.&lt;/p&gt;</description>
  <pubDate>Thu, 29 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Old post</title><link>https://lab.example/old</link>
  <description>Old</description><pubDate>Mon, 05 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Undated post</title><link>https://lab.example/undated</link>
  <description>No date</description></item>
<item><title>No link</title><description>x</description>
  <pubDate>Thu, 29 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

RELEASES_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Release notes from claude-code</title>
<entry><id>tag:github.com,2008:Repository/1/v2.1.0</id>
  <updated>2026-10-30T18:00:00Z</updated>
  <link rel="alternate" type="text/html" href="https://github.com/anthropics/claude-code/releases/tag/v2.1.0"/>
  <title>v2.1.0</title>
  <content type="html">&lt;ul&gt;&lt;li&gt;Added hooks&lt;/li&gt;&lt;/ul&gt;</content></entry>
</feed>"""


def source_serving(body: str, status: int = 200) -> RssFeedSource:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    return RssFeedSource(httpx.Client(transport=transport))


def test_parses_rss_keeping_dated_linked_items_in_window() -> None:
    [item] = source_serving(RSS).fetch("Lab", "https://lab.example/feed", WINDOW)
    assert item.title == "New model released"
    assert item.url == "https://lab.example/new-model"
    assert item.summary == "We release a new model & tools."
    assert item.source == "Lab"
    assert item.published == datetime(2026, 10, 29, 9, tzinfo=UTC)


def test_parses_github_release_atom_content() -> None:
    [item] = source_serving(RELEASES_ATOM).fetch("Claude Code", "https://x", WINDOW)
    assert item.title == "v2.1.0"
    assert item.summary == "Added hooks"
    assert item.url.endswith("/releases/tag/v2.1.0")


def test_garbage_is_a_source_error() -> None:
    with pytest.raises(SourceError, match="Lab"):
        source_serving("<html>not a feed").fetch("Lab", "https://x", WINDOW)


def test_html_to_text_collapses_whitespace() -> None:
    assert html_to_text("<p>a</p>\n<p>b  c</p>") == "a b c"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_rss.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/adapters/rss.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.models import FeedItem
from weekly_ai_newsletter.domain.window import TimeWindow


class RssFeedSource:
    """Items of one RSS/Atom feed published within a time window."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        response = get_with_retry(self._client, url)
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise SourceError(f"feed {name!r} could not be parsed: {feed.get('bozo_exception')}")
        items: list[FeedItem] = []
        for entry in feed.entries:
            published = _published(entry)
            link = entry.get("link")
            if published is None or not link or not window.contains(published):
                continue
            items.append(
                FeedItem(
                    title=html_to_text(entry.get("title", "")),
                    url=link,
                    summary=html_to_text(_body(entry)),
                    published=published,
                    source=name,
                )
            )
        return items


def html_to_text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    return " ".join(text.split())


def _published(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


def _body(entry: Any) -> str:
    if entry.get("content"):
        return str(entry.content[0].get("value", ""))
    return str(entry.get("summary", ""))
```

Note: if `test_html_to_text_collapses_whitespace` fails because `get_text(" ")` yields `"a  b  c"`, the `split()`/`join` already normalises it; if it yields `"ab c"`, keep the `" "` separator (it is what inserts the space between `<p>` blocks).

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/adapters -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Live-check every configured feed (network, not a test)**

Run:
```bash
uv run python - <<'EOF'
from datetime import date, timedelta
import yaml
from weekly_ai_newsletter.adapters.http import make_http_client
from weekly_ai_newsletter.adapters.rss import RssFeedSource
from weekly_ai_newsletter.domain.window import TimeWindow

window = TimeWindow.week_before(date.today() + timedelta(days=1))
window = TimeWindow(window.start - timedelta(days=60), window.end)  # wide, to see items
sources = yaml.safe_load(open("config/sources.yaml"))
with make_http_client() as http:
    feed_source = RssFeedSource(http)
    for group in ("news", "devtools"):
        for feed in sources[group]:
            try:
                items = feed_source.fetch(feed["name"], feed["url"], window)
                print(f"OK   {group:8} {feed['name']:22} {len(items):3} items (60 days)")
            except Exception as exc:
                print(f"FAIL {group:8} {feed['name']:22} {type(exc).__name__}: {exc}")
EOF
```
Expected: one line per feed. For each `FAIL` or `0 items`: search for the feed's current official RSS/Atom URL and replace it in `config/sources.yaml`; if none exists, remove the entry and note it in the commit message. Re-run until every remaining feed is `OK` with items. Report the final list to the user.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/adapters/rss.py tests/adapters/test_rss.py config/sources.yaml
git commit -m "feat: add RSS/Atom feed source and verify configured feeds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: GitHub Trending adapter

**Files:**
- Create: `adapters/github_trending.py`, `tests/fixtures/github_trending.html`, `tests/adapters/test_github_trending.py`

**Interfaces:**
- Consumes: `get_with_retry`, `Repo`, `SourceError`.
- Produces: `TRENDING_URL = "https://github.com/trending"`, `parse_trending_page(html: str) -> list[Repo]` (raises `SourceError` when no repository can be parsed), `GithubTrendingSource(client, *, languages: Sequence[str] = ("", "python"))` implementing `TrendingSource` (dedupes by `full_name`, first occurrence wins).

- [ ] **Step 1: Write the fixture**

`tests/fixtures/github_trending.html` (mirrors the real page structure):
```html
<html><body><div class="Box">
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/acme/agent-kit" data-view-component="true" class="Link">
      <span class="text-normal">acme /</span> agent-kit</a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
      Build reliable   LLM agents
  </p>
  <div class="f6 color-fg-muted mt-2">
    <span class="d-inline-block ml-0 mr-3">
      <span class="repo-language-color"></span>
      <span itemprop="programmingLanguage">Python</span>
    </span>
    <a href="/acme/agent-kit/stargazers" class="Link Link--muted d-inline-block mr-3"><svg></svg> 12,345</a>
    <a href="/acme/agent-kit/forks" class="Link Link--muted d-inline-block mr-3"><svg></svg> 1,024</a>
    <span class="d-inline-block mr-3">Built by <a href="/alice"><img alt="@alice"></a></span>
    <span class="d-inline-block float-sm-right"><svg></svg> 2,345 stars this week</span>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/someone/awesome-llm"><span class="text-normal">someone /</span> awesome-llm</a>
  </h2>
  <div class="f6 color-fg-muted mt-2">
    <a href="/someone/awesome-llm/stargazers" class="Link Link--muted d-inline-block mr-3"><svg></svg> 900</a>
    <span class="d-inline-block float-sm-right"><svg></svg> 150 stars this week</span>
  </div>
</article>
</div></body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/adapters/test_github_trending.py`:
```python
from pathlib import Path

import httpx
import pytest

from weekly_ai_newsletter.adapters.github_trending import GithubTrendingSource, parse_trending_page
from weekly_ai_newsletter.domain.errors import SourceError

FIXTURE = (Path(__file__).parents[1] / "fixtures" / "github_trending.html").read_text()


def test_parses_repositories_from_trending_page() -> None:
    first, second = parse_trending_page(FIXTURE)
    assert first.full_name == "acme/agent-kit"
    assert first.url == "https://github.com/acme/agent-kit"
    assert first.description == "Build reliable LLM agents"
    assert first.language == "Python"
    assert (first.stars, first.stars_this_week) == (12345, 2345)
    assert second.full_name == "someone/awesome-llm"
    assert (second.description, second.language, second.stars_this_week) == ("", None, 150)


def test_page_without_repositories_signals_a_layout_change() -> None:
    with pytest.raises(SourceError, match="layout"):
        parse_trending_page("<html><body>nothing here</body></html>")


def test_fetches_each_language_and_dedupes() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.url.path}?{request.url.query.decode()}")
        return httpx.Response(200, text=FIXTURE)

    source = GithubTrendingSource(
        httpx.Client(transport=httpx.MockTransport(handler)), languages=("", "python")
    )
    repos = source.fetch_weekly()
    assert paths == ["/trending?since=weekly", "/trending/python?since=weekly"]
    assert [r.full_name for r in repos] == ["acme/agent-kit", "someone/awesome-llm"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_github_trending.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

`src/weekly_ai_newsletter/adapters/github_trending.py`:
```python
from __future__ import annotations

import re
from collections.abc import Sequence

import httpx
from bs4 import BeautifulSoup

from weekly_ai_newsletter.adapters.http import get_with_retry
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.models import Repo

TRENDING_URL = "https://github.com/trending"
_STARS_THIS_WEEK = re.compile(r"([\d,]+)\s+stars\s+this\s+week")


class GithubTrendingSource:
    """Weekly trending repositories, scraped from github.com/trending (no official API)."""

    def __init__(self, client: httpx.Client, *, languages: Sequence[str] = ("", "python")) -> None:
        self._client = client
        self._languages = languages

    def fetch_weekly(self) -> list[Repo]:
        repos: dict[str, Repo] = {}
        for language in self._languages:
            url = f"{TRENDING_URL}/{language}" if language else TRENDING_URL
            response = get_with_retry(self._client, url, params={"since": "weekly"})
            for repo in parse_trending_page(response.text):
                repos.setdefault(repo.full_name, repo)
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
```

- [ ] **Step 5: Run tests, checks and a live smoke check**

Run: `uv run pytest tests/adapters -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

Then (network, not a test):
```bash
uv run python -c "
from weekly_ai_newsletter.adapters.http import make_http_client
from weekly_ai_newsletter.adapters.github_trending import GithubTrendingSource
with make_http_client() as http:
    repos = GithubTrendingSource(http).fetch_weekly()
print(len(repos)); [print(r) for r in repos[:3]]"
```
Expected: ~25–50 repos with non-zero `stars_this_week` and plausible descriptions. If parsing fails, save the live HTML, adjust selectors, and update the fixture to match the real structure.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/adapters/github_trending.py tests/fixtures tests/adapters/test_github_trending.py
git commit -m "feat: add GitHub Trending weekly source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Claude adapter

**Files:**
- Create: `adapters/claude.py`, `tests/adapters/test_claude.py`

**Interfaces:**
- Consumes: `LLMOutputError`; anthropic SDK (`anthropic.Anthropic`, `anthropic.types.ToolUseBlock`).
- Produces: `ClaudeClient(client: anthropic.Anthropic, *, model: str, max_tokens: int, max_attempts: int = 2)` implementing `LLMClient` via a forced tool call whose `input_schema` is `output_model.model_json_schema()`; `ClaudeClient.from_api_key(api_key: str, *, model: str, max_tokens: int) -> ClaudeClient` (SDK `max_retries=3`, `timeout=120`).

- [ ] **Step 1: Write the failing tests**

`tests/adapters/test_claude.py`:
```python
from typing import Any, cast

import anthropic
import pytest
from anthropic.types import TextBlock, ToolUseBlock
from pydantic import BaseModel

from weekly_ai_newsletter.adapters.claude import ClaudeClient
from weekly_ai_newsletter.domain.errors import LLMOutputError


class Answer(BaseModel):
    value: int


class FakeMessages:
    def __init__(self, *tool_inputs: dict[str, Any] | None) -> None:
        self._inputs = list(tool_inputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        tool_input = self._inputs.pop(0)
        if tool_input is None:
            content: list[Any] = [TextBlock(type="text", text="I refuse to use the tool")]
        else:
            content = [ToolUseBlock(type="tool_use", id="t1", name="submit_result", input=tool_input)]

        class Response:
            pass

        response = Response()
        response.content = content  # type: ignore[attr-defined]
        return response


def claude_with(messages: FakeMessages) -> ClaudeClient:
    class FakeAnthropic:
        pass

    fake = FakeAnthropic()
    fake.messages = messages  # type: ignore[attr-defined]
    return ClaudeClient(cast(anthropic.Anthropic, fake), model="claude-sonnet-5-5", max_tokens=1000)


def test_forces_a_tool_call_with_the_output_schema() -> None:
    messages = FakeMessages({"value": 42})
    answer = claude_with(messages).structured(system="sys", prompt="hi", output_model=Answer)
    assert answer == Answer(value=42)
    call = messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_result"}
    assert call["tools"][0]["input_schema"] == Answer.model_json_schema()


def test_retries_once_on_invalid_output() -> None:
    messages = FakeMessages({"value": "not a number"}, {"value": 1})
    assert claude_with(messages).structured(system="s", prompt="p", output_model=Answer).value == 1
    assert len(messages.calls) == 2


def test_raises_after_two_invalid_outputs() -> None:
    messages = FakeMessages(None, {"wrong": 1})
    with pytest.raises(LLMOutputError, match="Answer"):
        claude_with(messages).structured(system="s", prompt="p", output_model=Answer)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_claude.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/adapters/claude.py`:
```python
from __future__ import annotations

import logging

import anthropic
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, ValidationError

from weekly_ai_newsletter.domain.errors import LLMOutputError

logger = logging.getLogger(__name__)

TOOL_NAME = "submit_result"


class ClaudeClient:
    """LLMClient backed by the Anthropic API; structured output via a forced tool call."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str,
        max_tokens: int,
        max_attempts: int = 2,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._max_attempts = max_attempts

    @classmethod
    def from_api_key(cls, api_key: str, *, model: str, max_tokens: int) -> ClaudeClient:
        client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=120.0)
        return cls(client, model=model, max_tokens=max_tokens)

    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        tool = {
            "name": TOOL_NAME,
            "description": f"Submit the result as a {output_model.__name__} object.",
            "input_schema": output_model.model_json_schema(),
        }
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],  # type: ignore[list-item]
                tool_choice={"type": "tool", "name": TOOL_NAME},
            )
            tool_input = next(
                (block.input for block in response.content if isinstance(block, ToolUseBlock)),
                None,
            )
            if tool_input is None:
                last_error = LLMOutputError("response contained no tool call")
            else:
                try:
                    return output_model.model_validate(tool_input)
                except ValidationError as exc:
                    last_error = exc
            logger.warning(
                "Invalid %s from Claude (attempt %d/%d): %s",
                output_model.__name__,
                attempt,
                self._max_attempts,
                last_error,
            )
        raise LLMOutputError(
            f"no valid {output_model.__name__} after {self._max_attempts} attempts"
        ) from last_error
```

If mypy reports the `# type: ignore[list-item]` as unused, remove it; if it reports a different code on `tools=`, use that code instead.

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/adapters -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/adapters/claude.py tests/adapters/test_claude.py
git commit -m "feat: add Claude client with validated structured output

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Resend email adapter

**Files:**
- Create: `adapters/resend.py`, `tests/adapters/test_resend.py`

**Interfaces:**
- Consumes: `OutgoingEmail`, `EmailDeliveryError`.
- Produces: `RESEND_API_URL = "https://api.resend.com/emails"`, `ResendEmailSender(client: httpx.Client, *, api_key: str)` implementing `EmailSender` (single POST with `Idempotency-Key`; any HTTP error or non-2xx → `EmailDeliveryError`).

- [ ] **Step 1: Write the failing tests**

`tests/adapters/test_resend.py`:
```python
import json

import httpx
import pytest

from weekly_ai_newsletter.adapters.resend import ResendEmailSender
from weekly_ai_newsletter.domain.errors import EmailDeliveryError
from weekly_ai_newsletter.domain.models import OutgoingEmail

EMAIL = OutgoingEmail(
    sender="onboarding@resend.dev",
    recipient="me@example.com",
    subject="Veille IA",
    html="<p>Hi</p>",
    text="Hi",
    idempotency_key="weekly-ai-newsletter-2026-11-04",
)


def test_posts_the_email_with_auth_and_idempotency_key() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "abc"})

    ResendEmailSender(httpx.Client(transport=httpx.MockTransport(handler)), api_key="re_key").send(EMAIL)
    [request] = captured
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["Authorization"] == "Bearer re_key"
    assert request.headers["Idempotency-Key"] == "weekly-ai-newsletter-2026-11-04"
    assert json.loads(request.content) == {
        "from": "onboarding@resend.dev",
        "to": ["me@example.com"],
        "subject": "Veille IA",
        "html": "<p>Hi</p>",
        "text": "Hi",
    }


def test_rejection_is_reported_without_leaking_the_key() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(422, json={"message": "bad from"}))
    sender = ResendEmailSender(httpx.Client(transport=transport), api_key="re_secret")
    with pytest.raises(EmailDeliveryError, match="422") as excinfo:
        sender.send(EMAIL)
    assert "re_secret" not in str(excinfo.value)


def test_network_failure_is_a_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    sender = ResendEmailSender(httpx.Client(transport=httpx.MockTransport(handler)), api_key="k")
    with pytest.raises(EmailDeliveryError):
        sender.send(EMAIL)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/test_resend.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/adapters/resend.py`:
```python
from __future__ import annotations

import httpx

from weekly_ai_newsletter.domain.errors import EmailDeliveryError
from weekly_ai_newsletter.domain.models import OutgoingEmail

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailSender:
    """EmailSender for the Resend API; the idempotency key prevents duplicate sends."""

    def __init__(self, client: httpx.Client, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    def send(self, message: OutgoingEmail) -> None:
        try:
            response = self._client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": message.idempotency_key,
                },
                json={
                    "from": message.sender,
                    "to": [message.recipient],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"could not reach Resend: {exc}") from exc
        if response.is_error:
            raise EmailDeliveryError(
                f"Resend rejected the email ({response.status_code}): {response.text[:300]}"
            )
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest tests/adapters -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/adapters/resend.py tests/adapters/test_resend.py
git commit -m "feat: add Resend email sender

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Newsletter renderer (HTML + text)

**Files:**
- Create: `src/weekly_ai_newsletter/rendering/__init__.py` (empty), `rendering/renderer.py`, `rendering/templates/newsletter.html.j2`, `rendering/templates/newsletter.txt.j2`, `tests/unit/test_renderer.py`

**Interfaces:**
- Consumes: `Newsletter`, `Section`, `SelectedPaper`, `NewsItem`, `DevToolGroup`, `CuratedRepo`, `MAX_TOTAL`.
- Produces: `RenderedNewsletter(subject: str, html: str, text: str)`, `NewsletterRenderer()`, `.render(newsletter: Newsletter) -> RenderedNewsletter`, `LABELS: dict[str, dict[str, str]]`, `format_issue_date(day: date, language: str) -> str`. Subject format: `"{title} — {formatted date}"`, e.g. `"Veille IA hebdo — 4 novembre 2026"`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_renderer.py`:
```python
from datetime import date

from tests.factories import make_paper, make_repo, make_score
from weekly_ai_newsletter.domain.models import (
    CuratedRepo,
    DevToolChange,
    DevToolGroup,
    NewsItem,
    SelectedPaper,
)
from weekly_ai_newsletter.domain.newsletter import Newsletter, Section
from weekly_ai_newsletter.rendering.renderer import NewsletterRenderer, format_issue_date

PAPER = SelectedPaper(
    paper=make_paper("2610.00001", title="Agents <that> plan & act"),
    score=make_score("2610.00001", relevance=9, novelty=8, evidence=7, depth=8, practical_utility=6),
    summary="Un résumé.",
    why_selected="Parce que.",
)


def newsletter(language: str = "fr", **overrides: object) -> Newsletter:
    fields: dict[str, object] = {
        "issue_date": date(2026, 11, 4),
        "language": language,
        "news": Section.ok([NewsItem("Model X", "https://n.example/x", "Lab", "Big.")]),
        "devtools": Section.ok(
            [DevToolGroup("Claude Code", (DevToolChange("v2.1.0", "https://gh.example/r", "Hooks."),))]
        ),
        "papers": Section.ok([PAPER]),
        "repos": Section.ok([CuratedRepo(make_repo("acme/agent-kit", stars_this_week=2345), "Utile.")]),
    }
    fields.update(overrides)
    return Newsletter(**fields)  # type: ignore[arg-type]


def test_subject_and_dates_are_localised() -> None:
    assert format_issue_date(date(2026, 11, 4), "fr") == "4 novembre 2026"
    assert format_issue_date(date(2026, 11, 4), "en") == "November 4, 2026"
    assert NewsletterRenderer().render(newsletter()).subject == "Veille IA hebdo — 4 novembre 2026"


def test_html_contains_every_section_with_links_and_score_breakdown() -> None:
    html = NewsletterRenderer().render(newsletter()).html
    for expected in (
        "Actualité IA",
        "https://n.example/x",
        "Claude Code",
        "https://gh.example/r",
        "https://arxiv.org/abs/2610.00001",
        "Un résumé.",
        "Parce que.",
        "Pertinence 9",
        "55/70",
        "https://github.com/acme/agent-kit",
        "2,345",
    ):
        assert expected in html, expected


def test_html_escapes_titles_but_text_keeps_them_readable() -> None:
    rendered = NewsletterRenderer().render(newsletter())
    assert "Agents &lt;that&gt; plan &amp; act" in rendered.html
    assert "Agents <that> plan & act" in rendered.text


def test_unavailable_and_empty_sections_show_notices() -> None:
    rendered = NewsletterRenderer().render(
        newsletter(repos=Section.unavailable("trending down"), papers=Section.ok([]))
    )
    assert "Rubrique indisponible cette semaine." in rendered.html
    # the HTML escapes the apostrophe (&#39;), so check the text version
    assert "Rien d'assez solide cette semaine." in rendered.text
    assert "trending down" not in rendered.html


def test_english_labels() -> None:
    rendered = NewsletterRenderer().render(newsletter(language="en"))
    assert rendered.subject == "Weekly AI digest — November 4, 2026"
    assert "Research papers" in rendered.html and "Relevance 9" in rendered.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the renderer**

`src/weekly_ai_newsletter/rendering/renderer.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from weekly_ai_newsletter.domain.models import MAX_TOTAL
from weekly_ai_newsletter.domain.newsletter import Newsletter

LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Veille IA hebdo",
        "news": "Actualité IA",
        "devtools": "Outils de dev IA",
        "papers": "Papiers de recherche",
        "repos": "Tendances GitHub",
        "unavailable": "Rubrique indisponible cette semaine.",
        "empty": "Rien de notable cette semaine.",
        "empty_papers": "Rien d'assez solide cette semaine.",
        "why_selected": "Pourquoi ce papier",
        "stars_this_week": "étoiles cette semaine",
        "relevance": "Pertinence",
        "novelty": "Nouveauté",
        "evidence": "Preuves",
        "depth": "Profondeur",
        "practical_utility": "Utilité",
        "footer": "Généré automatiquement par weekly-ai-newsletter.",
    },
    "en": {
        "title": "Weekly AI digest",
        "news": "AI news",
        "devtools": "AI dev tools",
        "papers": "Research papers",
        "repos": "GitHub trending",
        "unavailable": "Section unavailable this week.",
        "empty": "Nothing notable this week.",
        "empty_papers": "Nothing solid enough this week.",
        "why_selected": "Why this paper",
        "stars_this_week": "stars this week",
        "relevance": "Relevance",
        "novelty": "Novelty",
        "evidence": "Evidence",
        "depth": "Depth",
        "practical_utility": "Utility",
        "footer": "Generated automatically by weekly-ai-newsletter.",
    },
}

_FRENCH_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def format_issue_date(day: date, language: str) -> str:
    if language == "fr":
        return f"{day.day} {_FRENCH_MONTHS[day.month - 1]} {day.year}"
    return f"{day:%B} {day.day}, {day.year}"


@dataclass(frozen=True)
class RenderedNewsletter:
    subject: str
    html: str
    text: str


class NewsletterRenderer:
    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("weekly_ai_newsletter", "rendering/templates"),
            autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, newsletter: Newsletter) -> RenderedNewsletter:
        labels = LABELS[newsletter.language]
        subject = f"{labels['title']} — {format_issue_date(newsletter.issue_date, newsletter.language)}"
        context = {
            "newsletter": newsletter,
            "labels": labels,
            "subject": subject,
            "date_label": format_issue_date(newsletter.issue_date, newsletter.language),
            "max_total": MAX_TOTAL,
        }
        return RenderedNewsletter(
            subject=subject,
            html=self._env.get_template("newsletter.html.j2").render(context),
            text=self._env.get_template("newsletter.txt.j2").render(context),
        )
```

Note: `f"{day:%B}"` depends on the C locale, which is English in CI and by default in Python; that is what the `en` test expects.

- [ ] **Step 4: Write the templates**

`src/weekly_ai_newsletter/rendering/templates/newsletter.html.j2`:
```jinja
{% macro heading(title) %}
<h2 style="font-size:18px;margin:32px 0 12px;padding-bottom:6px;border-bottom:2px solid #6366f1;">{{ title }}</h2>
{% endmacro %}
{% macro notice(text) %}
<p style="margin:0;color:#71717a;font-style:italic;">{{ text }}</p>
{% endmacro %}
{% macro section_body(section, empty_label) %}
{% if not section.available %}{{ notice(labels.unavailable) }}{% elif not section.items %}{{ notice(empty_label) }}{% else %}{{ caller() }}{% endif %}
{% endmacro %}
<!doctype html>
<html lang="{{ newsletter.language }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ subject }}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#18181b;line-height:1.55;">
<div style="background:#ffffff;border-radius:12px;padding:24px;">
<h1 style="font-size:24px;margin:0 0 4px;">{{ labels.title }}</h1>
<p style="margin:0;color:#71717a;">{{ date_label }}</p>

{{ heading(labels.news) }}
{% call section_body(newsletter.news, labels.empty) %}
{% for item in newsletter.news.items %}
<div style="margin:0 0 16px;">
<a href="{{ item.url }}" style="color:#4338ca;font-weight:600;text-decoration:none;">{{ item.title }}</a>
<span style="color:#71717a;font-size:13px;"> · {{ item.source }}</span>
<p style="margin:4px 0 0;">{{ item.summary }}</p>
</div>
{% endfor %}
{% endcall %}

{{ heading(labels.devtools) }}
{% call section_body(newsletter.devtools, labels.empty) %}
{% for group in newsletter.devtools.items %}
<h3 style="font-size:15px;margin:16px 0 6px;">{{ group.tool }}</h3>
<ul style="margin:0;padding-left:20px;">
{% for change in group.changes %}
<li style="margin:0 0 6px;"><a href="{{ change.url }}" style="color:#4338ca;">{{ change.title }}</a> — {{ change.summary }}</li>
{% endfor %}
</ul>
{% endfor %}
{% endcall %}

{{ heading(labels.papers) }}
{% call section_body(newsletter.papers, labels.empty_papers) %}
{% for item in newsletter.papers.items %}
{% set s = item.score %}
<div style="margin:0 0 24px;">
<a href="{{ item.paper.url }}" style="color:#4338ca;font-weight:600;font-size:16px;text-decoration:none;">{{ item.paper.title }}</a>
<p style="margin:2px 0 8px;color:#71717a;font-size:13px;">{{ item.paper.authors[:3] | join(", ") }}{% if item.paper.authors | length > 3 %} et al.{% endif %}</p>
<p style="margin:0 0 8px;">{{ item.summary }}</p>
<p style="margin:0 0 8px;"><strong>{{ labels.why_selected }} :</strong> {{ item.why_selected }}</p>
<p style="margin:0;font-size:12px;color:#52525b;background:#f4f4f5;border-radius:6px;padding:6px 10px;">
{{ labels.relevance }} {{ s.relevance }} · {{ labels.novelty }} {{ s.novelty }} · {{ labels.evidence }} {{ s.evidence }} · {{ labels.depth }} {{ s.depth }} · {{ labels.practical_utility }} {{ s.practical_utility }} → <strong>{{ s.total }}/{{ max_total }}</strong>
</p>
</div>
{% endfor %}
{% endcall %}

{{ heading(labels.repos) }}
{% call section_body(newsletter.repos, labels.empty) %}
{% for item in newsletter.repos.items %}
<div style="margin:0 0 14px;">
<a href="{{ item.repo.url }}" style="color:#4338ca;font-weight:600;text-decoration:none;">{{ item.repo.full_name }}</a>
<span style="color:#71717a;font-size:13px;"> · ★ +{{ "{:,}".format(item.repo.stars_this_week) }} {{ labels.stars_this_week }}{% if item.repo.language %} · {{ item.repo.language }}{% endif %}</span>
{% if item.repo.description %}<p style="margin:4px 0 0;color:#3f3f46;">{{ item.repo.description }}</p>{% endif %}
<p style="margin:4px 0 0;">{{ item.why_interesting }}</p>
</div>
{% endfor %}
{% endcall %}

<p style="margin:32px 0 0;font-size:12px;color:#a1a1aa;">{{ labels.footer }}</p>
</div>
</div>
</body>
</html>
```

`src/weekly_ai_newsletter/rendering/templates/newsletter.txt.j2`:
```jinja
{% macro section_body(section, empty_label) %}
{% if not section.available %}{{ labels.unavailable }}
{% elif not section.items %}{{ empty_label }}
{% else %}{{ caller() }}{% endif %}
{% endmacro %}
{{ subject }}
{{ "=" * subject | length }}

## {{ labels.news }}

{% call section_body(newsletter.news, labels.empty) %}
{% for item in newsletter.news.items %}
- {{ item.title }} ({{ item.source }})
  {{ item.url }}
  {{ item.summary }}

{% endfor %}
{% endcall %}

## {{ labels.devtools }}

{% call section_body(newsletter.devtools, labels.empty) %}
{% for group in newsletter.devtools.items %}
### {{ group.tool }}
{% for change in group.changes %}
- {{ change.title }}: {{ change.summary }}
  {{ change.url }}
{% endfor %}

{% endfor %}
{% endcall %}

## {{ labels.papers }}

{% call section_body(newsletter.papers, labels.empty_papers) %}
{% for item in newsletter.papers.items %}
{% set s = item.score %}
- {{ item.paper.title }}
  {{ item.paper.url }}
  {{ item.summary }}
  {{ labels.why_selected }} : {{ item.why_selected }}
  {{ labels.relevance }} {{ s.relevance }} · {{ labels.novelty }} {{ s.novelty }} · {{ labels.evidence }} {{ s.evidence }} · {{ labels.depth }} {{ s.depth }} · {{ labels.practical_utility }} {{ s.practical_utility }} → {{ s.total }}/{{ max_total }}

{% endfor %}
{% endcall %}

## {{ labels.repos }}

{% call section_body(newsletter.repos, labels.empty) %}
{% for item in newsletter.repos.items %}
- {{ item.repo.full_name }} (+{{ "{:,}".format(item.repo.stars_this_week) }} {{ labels.stars_this_week }})
  {{ item.repo.url }}
  {{ item.why_interesting }}

{% endfor %}
{% endcall %}
--
{{ labels.footer }}
```

- [ ] **Step 5: Run tests and checks**

Run: `uv run pytest tests/unit/test_renderer.py -v && uv run mypy src tests && uv run ruff check .`
Expected: all PASS. If the `"{:,}".format(...)` call is rejected by Jinja's sandbox rules (it is not sandboxed here, so it should work), replace it with a `thousands` filter registered on the environment.

- [ ] **Step 6: Visual check**

Run:
```bash
uv run python -c "
from tests.unit.test_renderer import newsletter
from weekly_ai_newsletter.rendering.renderer import NewsletterRenderer
open('preview.html','w').write(NewsletterRenderer().render(newsletter()).html)"
open preview.html
```
Expected: the page reads cleanly at phone and desktop width. (`preview.html` is gitignored.)

- [ ] **Step 7: Commit**

```bash
git add src/weekly_ai_newsletter/rendering tests/unit/test_renderer.py
git commit -m "feat: render the newsletter as HTML and plain text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Pipeline orchestration and composition root

**Files:**
- Create: `src/weekly_ai_newsletter/pipeline.py`, `src/weekly_ai_newsletter/bootstrap.py`, `tests/pipeline/__init__.py` (empty), `tests/pipeline/test_pipeline.py`
- Modify: `tests/fakes.py` (add source/sender/history fakes and `make_config`)

**Interfaces:**
- Consumes: everything from Tasks 2–15.
- Produces:
  - `Dependencies(papers: PaperSource, feeds: FeedSource, trending: TrendingSource, llm: LLMClient, history: HistoryStore)`
  - `Delivery(sender: EmailSender, from_address: str, to_address: str)`
  - `RunReport(issue_date, stages: dict[str, str], failures: dict[str, str], warnings: list[str])`, `.to_markdown() -> str`
  - `BuildResult(newsletter, rendered, report)`
  - `NewsletterPipeline(config: AppConfig, deps: Dependencies, *, delivery: Delivery | None = None, renderer: NewsletterRenderer | None = None)`, `.build(run_date: date) -> BuildResult` (raises `PipelineError` if all sections unavailable), `.publish(result: BuildResult) -> None` (send → write `archive/<date>.html` → record and save history; raises `PipelineError` if `delivery` is None)
  - `build_pipeline(config: AppConfig, secrets: Secrets, http: httpx.Client) -> NewsletterPipeline` in `bootstrap.py`
  - In `tests/fakes.py`: `FakePaperSource`, `FakeFeedSource`, `FakeTrendingSource`, `FakeEmailSender`, `InMemoryHistoryStore`, `make_config(tmp_path: Path) -> AppConfig`, `happy_llm() -> FakeLLM`

- [ ] **Step 1: Extend the fakes**

Append to `tests/fakes.py`:
```python
import json
from collections.abc import Sequence
from pathlib import Path

from tests.factories import make_score
from weekly_ai_newsletter.config import (
    AppConfig,
    FeedConfig,
    Keywords,
    PaperKeywords,
    PaperSettings,
    RepoKeywords,
    Settings,
    Sources,
)
from weekly_ai_newsletter.domain.history import History
from weekly_ai_newsletter.domain.models import FeedItem, OutgoingEmail, Paper, Repo
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.services.devtools_curator import ChangePick, DevToolsSelection, ToolGroup
from weekly_ai_newsletter.services.news_curator import NewsPick, NewsSelection
from weekly_ai_newsletter.services.paper_scorer import PaperScoreBatch
from weekly_ai_newsletter.services.paper_writer import PaperWriteup, PaperWriteupBatch
from weekly_ai_newsletter.services.repo_curator import RepoVerdict, RepoVerdicts

NEWS_FEED = "https://lab.example/feed"
DEVTOOLS_FEED = "https://github.com/anthropics/claude-code/releases.atom"


class FakePaperSource:
    def __init__(self, papers: Sequence[Paper] | Exception = ()) -> None:
        self._papers = papers
        self.windows: list[TimeWindow] = []

    def fetch(self, categories: Sequence[str], window: TimeWindow) -> list[Paper]:
        self.windows.append(window)
        if isinstance(self._papers, Exception):
            raise self._papers
        return list(self._papers)


class FakeFeedSource:
    def __init__(self, items_by_url: dict[str, Sequence[FeedItem] | Exception]) -> None:
        self._items = items_by_url

    def fetch(self, name: str, url: str, window: TimeWindow) -> list[FeedItem]:
        items = self._items.get(url, [])
        if isinstance(items, Exception):
            raise items
        return list(items)


class FakeTrendingSource:
    def __init__(self, repos: Sequence[Repo] | Exception = ()) -> None:
        self._repos = repos

    def fetch_weekly(self) -> list[Repo]:
        if isinstance(self._repos, Exception):
            raise self._repos
        return list(self._repos)


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    def send(self, message: OutgoingEmail) -> None:
        self.sent.append(message)


class InMemoryHistoryStore:
    def __init__(self, history: History | None = None) -> None:
        self.history = history or History()
        self.saves = 0

    def load(self) -> History:
        return History(entries={k: dict(v) for k, v in self.history.entries.items()})

    def save(self, history: History) -> None:
        self.history = history
        self.saves += 1


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        settings=Settings(
            papers=PaperSettings(categories=["cs.AI"]),
            history_path=tmp_path / "state" / "history.json",
            archive_dir=tmp_path / "archive",
        ),
        sources=Sources(
            news=[FeedConfig(name="Lab", url=NEWS_FEED)],
            devtools=[FeedConfig(name="Claude Code", url=DEVTOOLS_FEED)],
        ),
        keywords=Keywords(
            papers=PaperKeywords(positive={"agent": 3}),
            repos=RepoKeywords(include=["llm", "agent"], exclude=["awesome"]),
        ),
    )


def happy_llm() -> FakeLLM:
    """An LLM that scores every paper highly and keeps every candidate."""

    def scores(prompt: str) -> BaseModel:
        ids = [p["arxiv_id"] for p in json.loads(prompt)]
        return PaperScoreBatch(scores=[make_score(i, relevance=9, novelty=8) for i in ids])

    def writeups(prompt: str) -> BaseModel:
        return PaperWriteupBatch(
            writeups=[
                PaperWriteup(arxiv_id=p["arxiv_id"], summary="Résumé.", why_selected="Utile.")
                for p in json.loads(prompt)
            ]
        )

    def news(prompt: str) -> BaseModel:
        return NewsSelection(
            picks=[NewsPick(index=p["index"], summary="Résumé.") for p in json.loads(prompt)]
        )

    def devtools(prompt: str) -> BaseModel:
        changes = [ChangePick(index=p["index"], summary="Nouveau.") for p in json.loads(prompt)]
        return DevToolsSelection(groups=[ToolGroup(tool="Claude Code", changes=changes)])

    def repos(prompt: str) -> BaseModel:
        return RepoVerdicts(
            verdicts=[
                RepoVerdict(full_name=r["full_name"], keep=True, why_interesting="Utile.")
                for r in json.loads(prompt)
            ]
        )

    return FakeLLM(
        {
            PaperScoreBatch: scores,
            PaperWriteupBatch: writeups,
            NewsSelection: news,
            DevToolsSelection: devtools,
            RepoVerdicts: repos,
        }
    )
```

Move the new imports to the top of the file so ruff's import sorting passes.

- [ ] **Step 2: Write the failing tests**

`tests/pipeline/test_pipeline.py`:
```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tests.factories import make_feed_item, make_paper, make_repo
from tests.fakes import (
    DEVTOOLS_FEED,
    NEWS_FEED,
    FakeEmailSender,
    FakeFeedSource,
    FakePaperSource,
    FakeTrendingSource,
    InMemoryHistoryStore,
    happy_llm,
    make_config,
)
from weekly_ai_newsletter.domain.errors import PipelineError, SourceError
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.pipeline import Delivery, Dependencies, NewsletterPipeline

RUN_DATE = date(2026, 11, 4)


def build(
    tmp_path: Path,
    *,
    papers: FakePaperSource | None = None,
    feeds: FakeFeedSource | None = None,
    trending: FakeTrendingSource | None = None,
    history: InMemoryHistoryStore | None = None,
    email: FakeEmailSender | None = None,
) -> NewsletterPipeline:
    deps = Dependencies(
        papers=papers or FakePaperSource([make_paper("2610.00001", title="Agent planning")]),
        feeds=feeds
        or FakeFeedSource(
            {
                NEWS_FEED: [make_feed_item("https://lab.example/x", title="Model X")],
                DEVTOOLS_FEED: [make_feed_item("https://gh.example/v2", title="v2.1.0")],
            }
        ),
        trending=trending or FakeTrendingSource([make_repo("acme/agent-kit")]),
        llm=happy_llm(),
        history=history or InMemoryHistoryStore(),
    )
    delivery = Delivery(email, "from@x.dev", "to@x.dev") if email else None
    return NewsletterPipeline(make_config(tmp_path), deps, delivery=delivery)


def test_build_and_publish_happy_path(tmp_path: Path) -> None:
    email, history = FakeEmailSender(), InMemoryHistoryStore()
    pipeline = build(tmp_path, email=email, history=history)
    result = pipeline.build(RUN_DATE)
    pipeline.publish(result)

    [sent] = email.sent
    assert sent.subject == "Veille IA hebdo — 4 novembre 2026"
    assert sent.idempotency_key == "weekly-ai-newsletter-2026-11-04"
    for expected in ("Model X", "v2.1.0", "Agent planning", "acme/agent-kit"):
        assert expected in sent.html
    assert (tmp_path / "archive" / "2026-11-04.html").read_text() == sent.html
    saved = history.history
    assert saved.was_sent(HistoryKind.PAPER, "2610.00001")
    assert saved.was_sent(HistoryKind.NEWS, "https://lab.example/x")
    assert saved.was_sent(HistoryKind.DEVTOOL, "https://gh.example/v2")
    assert saved.was_sent(HistoryKind.REPO, "acme/agent-kit")
    assert "papers" in result.report.stages and not result.report.failures


def test_failing_section_degrades_without_sinking_the_newsletter(tmp_path: Path) -> None:
    pipeline = build(tmp_path, trending=FakeTrendingSource(SourceError("layout changed")))
    result = pipeline.build(RUN_DATE)
    assert not result.newsletter.repos.available
    assert result.newsletter.papers.available
    assert "layout changed" in result.report.failures["repos"]
    assert "Rubrique indisponible cette semaine." in result.rendered.html


def test_every_section_failing_is_fatal(tmp_path: Path) -> None:
    boom = SourceError("down")
    pipeline = build(
        tmp_path,
        papers=FakePaperSource(boom),
        feeds=FakeFeedSource({NEWS_FEED: boom, DEVTOOLS_FEED: boom}),
        trending=FakeTrendingSource(boom),
    )
    with pytest.raises(PipelineError):
        pipeline.build(RUN_DATE)


def test_quiet_week_is_not_a_failure(tmp_path: Path) -> None:
    pipeline = build(tmp_path, papers=FakePaperSource([]), feeds=FakeFeedSource({}))
    result = pipeline.build(RUN_DATE)
    assert result.newsletter.papers.available and result.newsletter.papers.items == ()
    assert result.newsletter.news.available and result.newsletter.news.items == ()
    assert "Rien d'assez solide cette semaine." in result.rendered.text


def test_one_broken_feed_is_a_warning_not_a_failure(tmp_path: Path) -> None:
    feeds = FakeFeedSource(
        {NEWS_FEED: SourceError("404"), DEVTOOLS_FEED: [make_feed_item("https://gh.example/v2")]}
    )
    result = build(tmp_path, feeds=feeds).build(RUN_DATE)
    assert not result.newsletter.news.available  # its only feed failed
    assert result.newsletter.devtools.available


def test_already_sent_items_are_not_resent(tmp_path: Path) -> None:
    previous = History()
    previous.record(HistoryKind.NEWS, ["https://lab.example/x"], date(2026, 10, 28))
    result = build(tmp_path, history=InMemoryHistoryStore(previous)).build(RUN_DATE)
    assert result.newsletter.news.items == ()


def test_paper_window_is_lagged_by_two_days(tmp_path: Path) -> None:
    papers = FakePaperSource([])
    build(tmp_path, papers=papers).build(RUN_DATE)
    [window] = papers.windows
    assert window.end == datetime(2026, 11, 2, tzinfo=UTC)


def test_publish_requires_delivery(tmp_path: Path) -> None:
    pipeline = build(tmp_path)
    with pytest.raises(PipelineError, match="delivery"):
        pipeline.publish(pipeline.build(RUN_DATE))


def test_report_markdown_lists_funnels_and_failures(tmp_path: Path) -> None:
    pipeline = build(tmp_path, trending=FakeTrendingSource(SourceError("layout changed")))
    markdown = pipeline.build(RUN_DATE).report.to_markdown()
    assert "| papers |" in markdown
    assert "**repos**" in markdown
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/pipeline -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'weekly_ai_newsletter.pipeline'`.

- [ ] **Step 4: Implement the pipeline**

`src/weekly_ai_newsletter/pipeline.py`:
```python
"""Orchestration: build four independent sections, render, then publish."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from weekly_ai_newsletter.config import AppConfig, FeedConfig
from weekly_ai_newsletter.domain.errors import LLMOutputError, PipelineError, SourceError
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.domain.models import (
    CuratedRepo,
    DevToolGroup,
    FeedItem,
    NewsItem,
    OutgoingEmail,
    SelectedPaper,
)
from weekly_ai_newsletter.domain.newsletter import Newsletter, Section
from weekly_ai_newsletter.domain.window import TimeWindow
from weekly_ai_newsletter.ports import (
    EmailSender,
    FeedSource,
    HistoryStore,
    LLMClient,
    PaperSource,
    TrendingSource,
)
from weekly_ai_newsletter.rendering.renderer import NewsletterRenderer, RenderedNewsletter
from weekly_ai_newsletter.services.dedup import drop_sent, unique_by
from weekly_ai_newsletter.services.devtools_curator import DevToolsCurator
from weekly_ai_newsletter.services.keyword_filter import KeywordFilter
from weekly_ai_newsletter.services.news_curator import NewsCurator
from weekly_ai_newsletter.services.paper_scorer import PaperScorer
from weekly_ai_newsletter.services.paper_selection import SelectionRules, select_papers
from weekly_ai_newsletter.services.paper_writer import PaperWriter
from weekly_ai_newsletter.services.repo_curator import RepoCurator
from weekly_ai_newsletter.services.repo_filter import RepoRuleFilter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dependencies:
    papers: PaperSource
    feeds: FeedSource
    trending: TrendingSource
    llm: LLMClient
    history: HistoryStore


@dataclass(frozen=True)
class Delivery:
    sender: EmailSender
    from_address: str
    to_address: str


@dataclass
class RunReport:
    issue_date: date
    stages: dict[str, str] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"## Newsletter {self.issue_date.isoformat()}", "", "| Section | Funnel |", "|---|---|"]
        lines += [f"| {name} | {funnel} |" for name, funnel in self.stages.items()]
        if self.failures:
            lines += ["", "### Unavailable sections", ""]
            lines += [f"- **{name}**: {error}" for name, error in self.failures.items()]
        if self.warnings:
            lines += ["", "### Warnings", ""]
            lines += [f"- {warning}" for warning in self.warnings]
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class BuildResult:
    newsletter: Newsletter
    rendered: RenderedNewsletter
    report: RunReport


class NewsletterPipeline:
    def __init__(
        self,
        config: AppConfig,
        deps: Dependencies,
        *,
        delivery: Delivery | None = None,
        renderer: NewsletterRenderer | None = None,
    ) -> None:
        settings = config.settings
        self._config = config
        self._deps = deps
        self._delivery = delivery
        self._renderer = renderer or NewsletterRenderer()
        self._keyword_filter = KeywordFilter(config.keywords.papers)
        self._repo_filter = RepoRuleFilter(config.keywords.repos)
        self._scorer = PaperScorer(deps.llm, batch_size=settings.papers.batch_size)
        self._writer = PaperWriter(deps.llm, language=settings.language)
        self._news_curator = NewsCurator(
            deps.llm, language=settings.language, max_items=settings.news.max_items
        )
        self._devtools_curator = DevToolsCurator(deps.llm, language=settings.language)
        self._repo_curator = RepoCurator(
            deps.llm, language=settings.language, max_items=settings.repos.max_items
        )
        self._rules = SelectionRules(
            min_total=settings.papers.min_total,
            min_novelty=settings.papers.min_novelty,
            max_selected=settings.papers.max_selected,
        )

    def build(self, run_date: date) -> BuildResult:
        history = self._deps.history.load()
        report = RunReport(issue_date=run_date)
        window = TimeWindow.week_before(run_date)
        newsletter = Newsletter(
            issue_date=run_date,
            language=self._config.settings.language,
            news=self._section("news", report, lambda: self._news(window, history, report)),
            devtools=self._section(
                "devtools", report, lambda: self._devtools(window, history, report)
            ),
            papers=self._section("papers", report, lambda: self._papers(run_date, history, report)),
            repos=self._section("repos", report, lambda: self._repos(run_date, history, report)),
        )
        if newsletter.all_unavailable:
            raise PipelineError("every section failed; refusing to send an empty newsletter")
        return BuildResult(newsletter, self._renderer.render(newsletter), report)

    def publish(self, result: BuildResult) -> None:
        if self._delivery is None:
            raise PipelineError("email delivery is not configured")
        newsletter = result.newsletter
        self._delivery.sender.send(
            OutgoingEmail(
                sender=self._delivery.from_address,
                recipient=self._delivery.to_address,
                subject=result.rendered.subject,
                html=result.rendered.html,
                text=result.rendered.text,
                idempotency_key=f"weekly-ai-newsletter-{newsletter.issue_date.isoformat()}",
            )
        )
        archive_dir = self._config.settings.archive_dir
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{newsletter.issue_date.isoformat()}.html"
        archive_path.write_text(result.rendered.html, encoding="utf-8")
        history = self._deps.history.load()
        _record_sent(history, newsletter)
        self._deps.history.save(history)

    def _section[T](
        self, name: str, report: RunReport, build: Callable[[], list[T]]
    ) -> Section[T]:
        try:
            return Section.ok(build())
        except Exception as exc:  # a broken section must never sink the whole newsletter
            logger.exception("Section %s failed", name)
            report.failures[name] = f"{type(exc).__name__}: {exc}"
            return Section.unavailable(str(exc))

    def _collect_feeds(
        self, feeds: Sequence[FeedConfig], window: TimeWindow, report: RunReport
    ) -> list[FeedItem]:
        items: list[FeedItem] = []
        failed = 0
        for feed in feeds:
            try:
                items.extend(self._deps.feeds.fetch(feed.name, feed.url, window))
            except Exception as exc:  # one broken feed must not hide the others
                failed += 1
                logger.warning("Feed %s (%s) failed: %s", feed.name, feed.url, exc)
                report.warnings.append(f"feed {feed.name} failed: {exc}")
        if feeds and failed == len(feeds):
            raise SourceError("every feed of this section failed")
        return items

    def _news(self, window: TimeWindow, history: History, report: RunReport) -> list[NewsItem]:
        settings = self._config.settings.news
        fetched = self._collect_feeds(self._config.sources.news, window, report)
        fresh = drop_sent(
            unique_by(fetched, key=lambda i: i.url),
            key=lambda i: i.url,
            history=history,
            kind=HistoryKind.NEWS,
        )
        fresh.sort(key=lambda i: i.published, reverse=True)
        candidates = fresh[: settings.max_candidates]
        curated = self._news_curator.curate(candidates)
        report.stages["news"] = (
            f"{len(fetched)} fetched -> {len(candidates)} candidates -> {len(curated)} selected"
        )
        return curated

    def _devtools(
        self, window: TimeWindow, history: History, report: RunReport
    ) -> list[DevToolGroup]:
        settings = self._config.settings.devtools
        fetched = self._collect_feeds(self._config.sources.devtools, window, report)
        fresh = drop_sent(
            unique_by(fetched, key=lambda i: i.url),
            key=lambda i: i.url,
            history=history,
            kind=HistoryKind.DEVTOOL,
        )
        fresh.sort(key=lambda i: i.published, reverse=True)
        candidates = fresh[: settings.max_candidates]
        groups = self._devtools_curator.curate(candidates)
        changes = sum(len(group.changes) for group in groups)
        report.stages["devtools"] = (
            f"{len(fetched)} fetched -> {len(candidates)} candidates -> "
            f"{changes} changes in {len(groups)} tools"
        )
        return groups

    def _papers(self, run_date: date, history: History, report: RunReport) -> list[SelectedPaper]:
        settings = self._config.settings.papers
        window = TimeWindow.week_before(run_date, lag_days=settings.window_lag_days)
        fetched = self._deps.papers.fetch(settings.categories, window)
        fresh = drop_sent(fetched, key=lambda p: p.arxiv_id, history=history, kind=HistoryKind.PAPER)
        shortlisted = self._keyword_filter.top(fresh, settings.prefilter_size)
        scored = self._scorer.score(shortlisted)
        if shortlisted and not scored:
            raise LLMOutputError("no paper could be scored")
        written = self._writer.write(select_papers(scored, self._rules))
        report.stages["papers"] = (
            f"{len(fetched)} fetched -> {len(shortlisted)} shortlisted -> "
            f"{len(scored)} scored -> {len(written)} selected"
        )
        return written

    def _repos(self, run_date: date, history: History, report: RunReport) -> list[CuratedRepo]:
        settings = self._config.settings.repos
        fetched = self._deps.trending.fetch_weekly()
        relevant = self._repo_filter.apply(fetched)
        fresh = drop_sent(
            relevant,
            key=lambda r: r.full_name,
            history=history,
            kind=HistoryKind.REPO,
            since=run_date - timedelta(weeks=settings.repeat_after_weeks),
        )
        curated = self._repo_curator.curate(fresh)
        report.stages["repos"] = (
            f"{len(fetched)} trending -> {len(fresh)} relevant -> {len(curated)} selected"
        )
        return curated


def _record_sent(history: History, newsletter: Newsletter) -> None:
    on = newsletter.issue_date
    history.record(HistoryKind.NEWS, (item.url for item in newsletter.news.items), on)
    history.record(
        HistoryKind.DEVTOOL,
        (change.url for group in newsletter.devtools.items for change in group.changes),
        on,
    )
    history.record(HistoryKind.PAPER, (p.paper.arxiv_id for p in newsletter.papers.items), on)
    history.record(HistoryKind.REPO, (r.repo.full_name for r in newsletter.repos.items), on)
```

Note on `test_quiet_week_is_not_a_failure`: `FakeFeedSource({})` returns `[]` for every feed (no exception), so news and devtools are available and empty, as expected.

`src/weekly_ai_newsletter/bootstrap.py`:
```python
"""Composition root: the only place that knows about concrete adapters."""

from __future__ import annotations

import httpx

from weekly_ai_newsletter.adapters.arxiv import ArxivPaperSource
from weekly_ai_newsletter.adapters.claude import ClaudeClient
from weekly_ai_newsletter.adapters.github_trending import GithubTrendingSource
from weekly_ai_newsletter.adapters.json_history import JsonHistoryStore
from weekly_ai_newsletter.adapters.resend import ResendEmailSender
from weekly_ai_newsletter.adapters.rss import RssFeedSource
from weekly_ai_newsletter.config import AppConfig, Secrets
from weekly_ai_newsletter.pipeline import Delivery, Dependencies, NewsletterPipeline


def build_pipeline(config: AppConfig, secrets: Secrets, http: httpx.Client) -> NewsletterPipeline:
    settings = config.settings
    deps = Dependencies(
        papers=ArxivPaperSource(http),
        feeds=RssFeedSource(http),
        trending=GithubTrendingSource(http, languages=settings.repos.trending_languages),
        llm=ClaudeClient.from_api_key(
            secrets.anthropic_api_key.get_secret_value(),
            model=settings.llm.model,
            max_tokens=settings.llm.max_tokens,
        ),
        history=JsonHistoryStore(settings.history_path),
    )
    delivery = None
    if secrets.email is not None:
        delivery = Delivery(
            sender=ResendEmailSender(http, api_key=secrets.email.resend_api_key.get_secret_value()),
            from_address=secrets.email.sender_email,
            to_address=secrets.email.recipient_email,
        )
    return NewsletterPipeline(config, deps, delivery=delivery)
```

- [ ] **Step 5: Run the full suite and checks**

Run: `uv run pytest -v && uv run mypy src tests && uv run ruff check . && uv run ruff format --check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/weekly_ai_newsletter/pipeline.py src/weekly_ai_newsletter/bootstrap.py tests
git commit -m "feat: orchestrate sections into a newsletter and publish it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Scheduling guard and CLI

**Files:**
- Create: `src/weekly_ai_newsletter/scheduling.py`, `src/weekly_ai_newsletter/cli.py`, `tests/unit/test_scheduling.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `Secrets`, `make_http_client`, `build_pipeline`, `RunReport`, `NewsletterError`, `ConfigError`.
- Produces: `PARIS = ZoneInfo("Europe/Paris")`, `is_send_time(now: datetime, *, hour: int = 7) -> bool`, `should_send(now: datetime, archive_dir: Path, *, hour: int = 7) -> bool`; `cli.main(argv: Sequence[str] | None = None) -> int` with subcommands `run [--dry-run] [--date YYYY-MM-DD] [--config-dir DIR] [--preview PATH]` and `should-send [--hour H] [--config-dir DIR]`. Exit codes: 0 ok, 1 run failure, 2 config/secrets error.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_scheduling.py`:
```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from weekly_ai_newsletter.scheduling import is_send_time, should_send


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 11, 4, 6, 10, tzinfo=UTC), True),  # winter: 07:10 Paris
        (datetime(2026, 11, 4, 5, 10, tzinfo=UTC), False),  # winter: 06:10 Paris
        (datetime(2026, 7, 1, 5, 25, tzinfo=UTC), True),  # summer: 07:25 Paris
        (datetime(2026, 7, 1, 6, 5, tzinfo=UTC), False),  # summer: 08:05 Paris
    ],
)
def test_send_time_follows_paris_daylight_saving(utc: datetime, expected: bool) -> None:
    assert is_send_time(utc) is expected


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        is_send_time(datetime(2026, 11, 4, 6))


def test_second_trigger_on_the_same_day_does_not_send(tmp_path: Path) -> None:
    now = datetime(2026, 11, 4, 6, 40, tzinfo=UTC)
    assert should_send(now, tmp_path)
    (tmp_path / "2026-11-04.html").write_text("sent")
    assert not should_send(now, tmp_path)
```

`tests/unit/test_cli.py`:
```python
from pathlib import Path

import httpx
import pytest

from tests.factories import make_feed_item, make_paper, make_repo
from tests.fakes import (
    DEVTOOLS_FEED,
    NEWS_FEED,
    FakeFeedSource,
    FakePaperSource,
    FakeTrendingSource,
    InMemoryHistoryStore,
    happy_llm,
)
from weekly_ai_newsletter import cli
from weekly_ai_newsletter.config import AppConfig, Secrets
from weekly_ai_newsletter.pipeline import Dependencies, NewsletterPipeline

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def fake_build_pipeline(config: AppConfig, secrets: Secrets, http: httpx.Client) -> NewsletterPipeline:
    deps = Dependencies(
        papers=FakePaperSource([make_paper(title="Agent planning")]),
        feeds=FakeFeedSource(
            {NEWS_FEED: [make_feed_item()], DEVTOOLS_FEED: [make_feed_item("https://gh.example/v")]}
        ),
        trending=FakeTrendingSource([make_repo()]),
        llm=happy_llm(),
        history=InMemoryHistoryStore(),
    )
    return NewsletterPipeline(config, deps)


def test_dry_run_writes_preview_without_email_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for name in ("RESEND_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAIL", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)
    preview = tmp_path / "preview.html"
    code = cli.main(
        ["run", "--dry-run", "--date", "2026-11-04", "--config-dir", str(REPO_CONFIG),
         "--preview", str(preview)]
    )
    assert code == 0
    assert "Agent planning" in preview.read_text()


def test_missing_secrets_exit_with_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["run", "--dry-run", "--config-dir", str(REPO_CONFIG)]) == 2


def test_real_run_without_email_secrets_exits_with_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert cli.main(["run", "--config-dir", str(REPO_CONFIG)]) == 2


def test_should_send_prints_a_boolean(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["should-send", "--config-dir", str(REPO_CONFIG)]) == 0
    assert capsys.readouterr().out.strip() in {"true", "false"}


def test_github_summary_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)
    cli.main(["run", "--dry-run", "--date", "2026-11-04", "--config-dir", str(REPO_CONFIG),
              "--preview", str(tmp_path / "p.html")])
    assert "| papers |" in summary.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_scheduling.py tests/unit/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/weekly_ai_newsletter/scheduling.py`:
```python
"""Send-time guard: GitHub cron is UTC-only and may fire late, Paris time has DST."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def is_send_time(now: datetime, *, hour: int = 7) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(PARIS).hour == hour


def should_send(now: datetime, archive_dir: Path, *, hour: int = 7) -> bool:
    """True at the send hour in Paris, unless today's issue was already archived."""
    if not is_send_time(now, hour=hour):
        return False
    today = now.astimezone(PARIS).date()
    return not (archive_dir / f"{today.isoformat()}.html").exists()
```

`src/weekly_ai_newsletter/cli.py`:
```python
"""Command-line entry point: `newsletter run` and `newsletter should-send`."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from weekly_ai_newsletter.adapters.http import make_http_client
from weekly_ai_newsletter.bootstrap import build_pipeline
from weekly_ai_newsletter.config import Secrets, load_config
from weekly_ai_newsletter.domain.errors import ConfigError, NewsletterError
from weekly_ai_newsletter.pipeline import RunReport
from weekly_ai_newsletter.scheduling import PARIS, should_send

logger = logging.getLogger("weekly_ai_newsletter")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "should-send":
        return _should_send(args)
    return _run(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsletter", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="build the newsletter and send it")
    run.add_argument("--dry-run", action="store_true", help="write a local preview, send nothing")
    run.add_argument("--date", type=date.fromisoformat, help="issue date (default: today in Paris)")
    run.add_argument("--config-dir", type=Path, default=Path("config"))
    run.add_argument("--preview", type=Path, default=Path("preview.html"))

    check = commands.add_parser("should-send", help="print true when it is time to send")
    check.add_argument("--hour", type=int, default=7)
    check.add_argument("--config-dir", type=Path, default=Path("config"))
    return parser


def _should_send(args: argparse.Namespace) -> int:
    config = load_config(args.config_dir)
    send = should_send(datetime.now(UTC), config.settings.archive_dir, hour=args.hour)
    print("true" if send else "false")
    return 0


def _run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config_dir)
        secrets = Secrets.from_env(os.environ, require_email=not args.dry_run)
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2
    run_date: date = args.date or datetime.now(PARIS).date()
    with make_http_client() as http:
        pipeline = build_pipeline(config, secrets, http)
        try:
            result = pipeline.build(run_date)
            if args.dry_run:
                args.preview.write_text(result.rendered.html, encoding="utf-8")
                logger.info("Preview written to %s", args.preview)
            else:
                pipeline.publish(result)
                logger.info("Newsletter %s sent", run_date.isoformat())
        except NewsletterError as exc:
            logger.error("Newsletter run failed: %s", exc)
            return 1
    _report(result.report)
    return 0


def _report(report: RunReport) -> None:
    markdown = report.to_markdown()
    logger.info("Run summary:\n%s", markdown)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for name, error in report.failures.items():
            print(f"::warning title=Section unavailable::{name}: {error}")
```

- [ ] **Step 4: Run tests and checks**

Run: `uv run pytest -v && uv run mypy src tests && uv run ruff check . && uv run ruff format --check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/weekly_ai_newsletter/scheduling.py src/weekly_ai_newsletter/cli.py tests/unit
git commit -m "feat: add CLI and Paris send-time guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: Scheduled workflow and README

**Files:**
- Create: `.github/workflows/newsletter.yml`, `README.md`

**Interfaces:**
- Consumes: CLI commands `newsletter should-send`, `newsletter run`; secrets `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`, `RECIPIENT_EMAIL`.
- Produces: weekly automation and project documentation.

- [ ] **Step 1: Write the workflow**

`.github/workflows/newsletter.yml`:
```yaml
name: Weekly newsletter

on:
  schedule:
    # 07:00 Europe/Paris is 06:00 UTC in winter and 05:00 UTC in summer;
    # both are scheduled and `newsletter should-send` keeps only the right one.
    - cron: "0 5 * * 3"
    - cron: "0 6 * * 3"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: weekly-newsletter
  cancel-in-progress: false

jobs:
  send:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.repository.default_branch }}
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked --no-dev

      - name: Check send time (Europe/Paris)
        id: gate
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "send=true" >> "$GITHUB_OUTPUT"
          else
            echo "send=$(uv run newsletter should-send)" >> "$GITHUB_OUTPUT"
          fi

      - name: Build and send the newsletter
        if: steps.gate.outputs.send == 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          RECIPIENT_EMAIL: ${{ secrets.RECIPIENT_EMAIL }}
        run: uv run newsletter run

      - name: Commit archive and history
        if: steps.gate.outputs.send == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add archive state
          if git diff --cached --quiet; then exit 0; fi
          git commit -m "chore: archive newsletter $(TZ=Europe/Paris date +%F)"
          git push
```

- [ ] **Step 2: Validate the workflow syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/newsletter.yml')); yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`. If `actionlint` is installed (`which actionlint`), also run `actionlint` and fix any finding.

- [ ] **Step 3: Write `README.md`**

````markdown
# weekly-ai-newsletter

[![CI](https://github.com/legallclaire/weekly-ai-newsletter/actions/workflows/ci.yml/badge.svg)](https://github.com/legallclaire/weekly-ai-newsletter/actions/workflows/ci.yml)

A weekly AI digest delivered by email every Wednesday at 07:00 (Paris time):

- **AI news**: the handful of stories that mattered this week
- **AI dev tools**: every notable release of AI coding tools (Claude Code, Codex, Cursor, Copilot, Gemini CLI…)
- **Research papers**: 0–3 arXiv papers that genuinely teach something, selected by a scoring rubric
- **GitHub trending**: up to 5 AI/ML repositories that gained the most stars this week

Past issues are in [`archive/`](archive/).

## How papers are selected

```
arXiv (8 categories, ~thousands/week)
  → keyword pre-filter (weighted, title counts double)      → top 50
  → Claude scores each abstract on 5 criteria (1–10)
  → total = 2·relevance + 2·novelty + evidence + depth + utility   (/70)
  → drop incremental work, novelty < 6, total < 45          → best 0–3
  → Claude writes a summary and "why it was selected"
```

The LLM only produces per-criterion scores; the aggregation and selection rules are plain,
tested Python, so they are deterministic and easy to tune in `config/settings.yaml`.
Every paper in the email shows its score breakdown.

## Architecture

Ports and adapters: the core never imports an HTTP client or an SDK.

```
src/weekly_ai_newsletter/
  domain/      pure models: Paper, PaperScore, Newsletter, Section, History…
  ports.py     Protocols: PaperSource, FeedSource, TrendingSource, LLMClient, EmailSender, HistoryStore
  services/    keyword filter, selection rules, LLM-backed curators, dedup
  adapters/    arXiv, RSS/Atom, GitHub Trending, Claude, Resend, JSON history
  rendering/   Jinja2 templates (HTML + plain text)
  prompts/     system prompts, versioned like code
  pipeline.py  builds four independent sections, then publishes
  bootstrap.py the only place that wires concrete adapters
```

Design choices:

- **Sections fail independently.** A broken feed or a layout change on GitHub Trending
  turns one section into a "unavailable this week" notice; the email still goes out.
- **The LLM never produces URLs.** It answers with indices or IDs that are mapped back to
  source data.
- **Structured output is validated.** Claude answers through a forced tool call whose
  schema is the Pydantic model; invalid output is retried once, then the batch is skipped.
- **Exactly one email per week.** Two UTC crons cover daylight saving time, a guard keeps
  the one at 07:00 Paris, and the archive file plus a Resend idempotency key prevent
  duplicates.
- **Tests run offline**: fakes for every port, recorded fixtures for every adapter.

## Run it locally

```bash
git clone https://github.com/legallclaire/weekly-ai-newsletter.git
cd weekly-ai-newsletter
uv sync
cp .env.example .env            # add your ANTHROPIC_API_KEY
uv run --env-file .env newsletter run --dry-run && open preview.html
```

`--date YYYY-MM-DD` rebuilds the issue of a given day.

## Deploy with GitHub Actions

1. Create a [Resend](https://resend.com) API key.
2. Add repository secrets: `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`
   (e.g. `onboarding@resend.dev`), `RECIPIENT_EMAIL`.
3. The `Weekly newsletter` workflow runs every Wednesday; trigger it manually from the
   Actions tab to test.

## Customise

| What | Where |
|---|---|
| Language (`fr` / `en`), thresholds, counts, model | `config/settings.yaml` |
| News and dev-tool feeds | `config/sources.yaml` |
| Paper keywords and weights, repo filters | `config/keywords.yaml` |
| Scoring rubric and writing instructions | `src/weekly_ai_newsletter/prompts/` |

Adding a source of a new kind means writing one adapter that satisfies a port in
`ports.py` and wiring it in `bootstrap.py`.

## Development

```bash
uv run pytest --cov=weekly_ai_newsletter
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
uv run pre-commit install
```

## License

MIT
````

- [ ] **Step 4: Run the full checks**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/newsletter.yml README.md
git commit -m "docs: add README and weekly GitHub Actions workflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Live dry run, tuning and publication

This task needs the user: an Anthropic API key for the dry run, and explicit approval before anything is pushed to GitHub.

**Files:**
- Possibly modify: `config/keywords.yaml`, `config/settings.yaml`, prompt templates
- Create: `docs/assets/newsletter-preview.png`
- Modify: `README.md` (add the screenshot)

- [ ] **Step 1: Real dry run**

Ask the user to create `.env` from `.env.example` with their `ANTHROPIC_API_KEY`, then run:
`uv run --env-file .env newsletter run --dry-run`
Expected: exit code 0, a run summary in the logs with non-zero counts for every section, and `preview.html` written.

- [ ] **Step 2: Review quality with the user**

Open `preview.html` and show it to the user. Check together: are the papers ones they would want to read, is anything clearly incremental, are dev-tool changes complete, are the repos relevant. Tune `config/keywords.yaml`, thresholds, or prompt wording based on feedback, re-run, and commit each tuning change separately with a message explaining why.

- [ ] **Step 3: Screenshot for the README**

Take a screenshot of the top of `preview.html` (≈ 900 px wide) and save it to `docs/assets/newsletter-preview.png`. Add under the README intro:
```markdown
![Newsletter preview](docs/assets/newsletter-preview.png)
```
Commit: `docs: add newsletter preview screenshot`.

- [ ] **Step 4: Publish to GitHub (only after explicit user approval)**

```bash
gh repo create legallclaire/weekly-ai-newsletter --public --source . --push \
  --description "Weekly AI digest: news, dev tools, research papers and trending repos, curated with Claude."
```
Then set the secrets (the user types the values; never echo them):
```bash
gh secret set ANTHROPIC_API_KEY
gh secret set RESEND_API_KEY
gh secret set SENDER_EMAIL
gh secret set RECIPIENT_EMAIL
```

- [ ] **Step 5: First real send**

Run: `gh workflow run "Weekly newsletter"` then `gh run watch`.
Expected: CI is green, the email arrives in the user's inbox (check spam the first time), and a bot commit adds `archive/<date>.html` and `state/history.json`.
