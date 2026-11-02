# Weekly AI Newsletter — Design Spec

- **Date:** 2026-11-02
- **Status:** Approved design, pending spec review
- **Repository:** `weekly-ai-newsletter`

## 1. Goal

Send one HTML email every **Wednesday at ~07:00 Europe/Paris** containing a curated
digest of the past 7 days in AI:

1. **AI News** — the 4–6 most important news items.
2. **AI Dev Tools** — exhaustive coverage of notable releases of AI coding tools
   (Claude Code, Codex, Cursor, Copilot, Gemini CLI…), grouped by tool.
3. **Research Papers** — 0 to 3 arXiv papers on LLM agents, inference, deployment,
   RAG, model evaluation, ML in general and ML-related statistics. Papers that only
   report a small benchmark gain, a minor architecture variant, or a renaming of an
   existing method are excluded. Papers that genuinely teach something are favoured,
   even when highly technical.
4. **GitHub Trending** — up to 5 relevant AI/ML repositories that gained the most
   stars during the week.

The newsletter language is configurable (`language: fr` by default). Code, comments,
docs and identifiers are written in English.

### Success criteria

- The email arrives every Wednesday morning without manual action.
- Selected papers are ones the reader would not want to have missed; weeks with
  nothing solid produce an explicit "nothing this week" rather than filler.
- A failing source degrades one section, never the whole newsletter.
- The whole pipeline is testable offline; CI runs lint, type-check and tests.

### Non-goals (v1)

- Reading full paper PDFs (abstracts only).
- Multiple recipients / subscription management.
- Web publication (GitHub Pages) — the committed HTML archive is enough for v1.

## 2. Technical choices

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Packaging | `uv`, `pyproject.toml`, `src/` layout |
| Models & config | Pydantic (v2), YAML config files |
| HTTP | `httpx` |
| RSS/Atom | `feedparser` |
| HTML parsing (Trending page) | `selectolax` or `beautifulsoup4` |
| LLM | Anthropic API (`anthropic` SDK), default model `claude-sonnet-5-5`, configurable |
| Email | Resend API |
| Templates | Jinja2 (HTML + plain-text versions) |
| Quality | `ruff` (lint + format), `mypy --strict`, `pytest`, `pytest-cov`, `pre-commit` |
| Scheduling | GitHub Actions cron |
| License | MIT |

## 3. Architecture — ports & adapters

Business logic (filtering, scoring arithmetic, selection, deduplication) depends only
on domain models and interfaces (ports). All I/O lives in adapters.

```
src/weekly_ai_newsletter/
  domain/        # Paper, NewsItem, DevToolUpdate, Repo, PaperScore, Newsletter, Section…
                 # pure dataclasses / Pydantic models, no I/O
  ports/         # Protocols: PaperSource, FeedSource, TrendingSource, LLMClient,
                 #            EmailSender, HistoryStore, Clock
  adapters/
    arxiv.py             # PaperSource via arXiv API
    rss.py               # FeedSource via feedparser
    github_trending.py   # TrendingSource via github.com/trending?since=weekly
    claude.py            # LLMClient via anthropic SDK (structured JSON output)
    resend.py            # EmailSender via Resend API
    json_history.py      # HistoryStore backed by state/history.json
  services/
    keyword_filter.py    # weighted keyword pre-filter for papers
    paper_scorer.py      # LLM scoring + Python aggregation + selection
    paper_writer.py      # LLM summary + "why selected" for retained papers
    news_curator.py      # LLM selection/summarisation of news
    devtools_curator.py  # LLM grouping of dev-tool releases
    repo_curator.py      # rule filter + LLM validation + ranking of repos
    dedup.py             # history-based deduplication
  rendering/
    renderer.py
    templates/newsletter.html.j2, newsletter.txt.j2
  config.py      # Settings (Pydantic), loads config/*.yaml + env vars
  pipeline.py    # orchestration
  cli.py         # `newsletter run [--dry-run] [--date YYYY-MM-DD]`
config/
  settings.yaml  # language, model, thresholds, counts, arXiv categories
  sources.yaml   # news feeds, dev-tool feeds
  keywords.yaml  # weighted positive/negative keywords (papers & repos)
prompts/         # prompt templates (versioned, reviewable)
state/history.json
archive/YYYY-MM-DD.html
tests/
  unit/  adapters/  pipeline/  fixtures/
.github/workflows/ci.yml, newsletter.yml
```

Adapters are wired in a single composition root (`pipeline.build_pipeline(settings)`),
so tests can inject fakes (`FakeLLMClient`, `FakeEmailSender`, …).

## 4. Data flow

The run computes a **time window once** (`[run_date - 7 days, run_date)`) and passes it
to every source, making runs reproducible (`--date` overrides the run date).

```
ArxivSource ──► ~thousands of papers ──► KeywordFilter ──► top 50 ──► PaperScorer ──► 0–3 ──► PaperWriter
FeedSource (news) ──► week's items ──► Dedup ──► NewsCurator ──► 4–6 items
FeedSource (dev tools) ──► week's items ──► Dedup ──► DevToolsCurator ──► updates grouped by tool
TrendingSource ──► ~50 repos ──► RepoRuleFilter ──► Dedup ──► RepoCurator ──► top 5 by stars gained
                                         │
                               Newsletter ──► Renderer (HTML + text) ──► EmailSender
                                         └──► archive/YYYY-MM-DD.html, state/history.json
```

Each section is built independently. A section failure yields a `Section` in an
"unavailable" state rendered as a short notice.

## 5. Sections in detail

### 5.1 Research papers

**Sources.** arXiv API, categories `cs.LG`, `cs.AI`, `cs.CL`, `stat.ML`, `cs.IR`,
`cs.MA`, `cs.SE`, `cs.DC` (configurable), filtered on submission date within the
window. Pagination respects arXiv's rate limit (≥ 3 s between requests). Papers are
deduplicated by arXiv ID (cross-lists appear once).

**Keyword pre-filter (pure Python).** `keywords.yaml` defines weighted terms per theme:
agents, inference/serving/quantization, deployment, RAG/retrieval, evaluation
(incl. contamination, LLM-as-judge), general ML, ML-related statistics (uncertainty,
Bayesian, conformal prediction, causal inference, calibration). Negative terms
(configurable, e.g. medical imaging, remote sensing) subtract weight.
`score = title_weight × title_matches + abstract_matches`; matching is
case-insensitive on word boundaries. The top `prefilter_size` (default 50) papers are kept.

**LLM scoring.** Abstracts are sent in batches of 10. For each paper Claude returns
structured JSON validated by Pydantic:

```json
{
  "arxiv_id": "2611.01234",
  "relevance": 9, "novelty": 8, "evidence": 7, "depth": 8, "practical_utility": 6,
  "is_incremental": false,
  "rationale": "one or two sentences per criterion"
}
```

The prompt describes each criterion with anchors (what deserves 2/10 vs 9/10), the
reader's interests, and the explicit exclusion rules (small benchmark gain, minor
architecture variant, renamed existing method). It states that a highly technical
paper that teaches something beats an accessible but incremental one.

**Aggregation (pure Python).**
`total = 2·relevance + 2·novelty + evidence + depth + practical_utility` (max 70).

**Selection rules** (all configurable):
1. Drop papers with `is_incremental = true` or `novelty < 6`.
2. Drop papers with `total < 45`.
3. Sort by `total` desc, tie-break by `relevance + novelty`, then arXiv ID.
4. Keep at most 3. Zero is a valid outcome ("Nothing solid enough this week").

**Writing.** A second call, only for retained papers, produces in the configured
language: a 4–6 sentence summary (problem, key idea, result) and a "why it was
selected" paragraph. Rendered per paper: title, authors (truncated), arXiv link,
summary, why selected, and the score breakdown
(`Relevance 9 · Novelty 8 · Evidence 7 · Depth 8 · Utility 6 → 55/70`).

### 5.2 AI news

**Sources.** RSS/Atom feeds listed in `sources.yaml` (e.g. Anthropic, OpenAI,
Google DeepMind, Hugging Face, Meta AI blogs, Simon Willison, Import AI, The Batch,
MIT Technology Review AI). Items within the window, deduplicated against history.

**Curation.** Claude selects the 4–6 most important items and writes a 2–3 sentence
summary each, with the source link.

### 5.3 AI dev tools

**Sources.** Dedicated feeds in `sources.yaml`: `anthropics/claude-code` GitHub
releases Atom feed, Anthropic news, OpenAI Codex, Cursor changelog, GitHub changelog
(Copilot), Gemini CLI releases, Simon Willison. This section bypasses the generic
importance selection to aim for exhaustiveness.

**Curation.** Claude groups all window items by tool and keeps notable changes
(features, behaviour changes, new models/integrations), dropping pure bug-fix noise.
Rendered as one block per tool with links to the release notes.

### 5.4 GitHub trending

1. **Candidates:** `github.com/trending?since=weekly` for all languages and Python;
   parse repo name, description, language, total stars, stars gained this week.
   Behind the `TrendingSource` port so an OSS Insight API adapter can replace it.
2. **Rule filter (pure Python):** keep repos whose description/topics match AI/ML
   keywords (llm, agent, rag, inference, mcp, ml…); exclude `awesome-*` lists,
   prompt collections and repos without code.
3. **Dedup:** skip repos sent in the last 8 weeks.
4. **LLM validation:** Claude confirms each candidate is a genuinely useful tool or
   library (not hype / list / clone) and writes a one-sentence "why it's interesting".
5. **Ranking:** by stars gained this week; keep at most 5.

Rendered per repo: name + link, stars gained this week, language, one-line
description, why it's interesting.

## 6. State & archive

- `state/history.json` stores sent arXiv IDs, news URLs, dev-tool release URLs and
  repo names with send dates. Repos may reappear after 8 weeks; papers and news never.
- `archive/YYYY-MM-DD.html` stores each rendered newsletter.
- Both are committed by the scheduled workflow after a successful send (not in
  `--dry-run`).

## 7. Error handling

- All HTTP calls: timeout + up to 3 retries with exponential backoff on 429/5xx/timeouts.
- Invalid LLM output (malformed JSON, out-of-range score): one retry; on second
  failure the batch is skipped and logged.
- Section failure → "unavailable this week" notice; the run continues and ends with a
  warning annotation.
- Global failure (LLM or email provider unreachable after retries, invalid config)
  → non-zero exit; GitHub notifies the repository owner.
- A run summary (counts per stage) is logged and written to the GitHub Actions job
  summary.
- Secrets (`ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `RECIPIENT_EMAIL`, `SENDER_EMAIL`)
  come only from environment variables; never logged. `.env.example` documents them.

## 8. Scheduling

`newsletter.yml` runs on two UTC crons covering CET and CEST
(`0 5 * * 3` and `0 6 * * 3`) plus `workflow_dispatch`. A guard step skips the run
unless the current Europe/Paris time is within the 07:00 hour window, so exactly one
send happens per week regardless of daylight saving time. Manual dispatch bypasses the
guard. GitHub cron delays of a few minutes are accepted.

## 9. Testing

All tests run offline.

- **Unit:** keyword filter, score aggregation, selection rules (threshold,
  incremental flag, novelty floor, ties, empty result), dedup and history expiry,
  time window computation, scheduling guard.
- **Adapters:** parsing of recorded fixtures (arXiv Atom XML, RSS feeds, Trending HTML,
  Claude JSON responses, Resend request payload via `httpx.MockTransport`).
- **Pipeline:** end-to-end with fakes; asserts rendered HTML content, section-failure
  degradation and the email handed to `FakeEmailSender`.
- Coverage measured with `pytest-cov` and reported in CI.

## 10. CI & repository hygiene

- `ci.yml` on push/PR: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest --cov`.
- `pre-commit` hooks mirror CI checks.
- README: pipeline diagram, architecture rationale (ports & adapters, deterministic
  scoring in Python), sample newsletter screenshot, 5-command setup,
  `newsletter run --dry-run`, how to add a source.
- MIT license, CI and coverage badges.

## 11. Configuration summary (defaults)

| Key | Default |
|---|---|
| `language` | `fr` |
| `llm.model` | `claude-sonnet-5-5` |
| `papers.categories` | `cs.LG, cs.AI, cs.CL, stat.ML, cs.IR, cs.MA, cs.SE, cs.DC` |
| `papers.prefilter_size` | `50` |
| `papers.batch_size` | `10` |
| `papers.min_total` | `45` |
| `papers.min_novelty` | `6` |
| `papers.max_selected` | `3` |
| `news.max_items` | `6` |
| `repos.max_items` | `5` |
| `repos.repeat_after_weeks` | `8` |
