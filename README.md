# weekly-ai-newsletter

[![CI](https://github.com/legallclaire/weekly-ai-newsletter/actions/workflows/ci.yml/badge.svg)](https://github.com/legallclaire/weekly-ai-newsletter/actions/workflows/ci.yml)

A weekly AI digest delivered by email every Wednesday at 07:00 (Paris time):

- **AI news**: the handful of stories that mattered this week
- **AI dev tools**: every notable release of AI coding tools (Claude Code, Codex, Cursor, Gemini CLI…);
  tools listed as secondary (e.g. Copilot) appear only for a major announcement
- **Research papers**: 0–3 arXiv papers that genuinely teach something, selected by a scoring rubric
- **GitHub trending**: up to 5 AI/ML repositories that gained the most stars this week
- **Skills & plugins**: up to 5 recent agent skills, coding-agent plugins and MCP servers
  (at most 2 MCP servers), found through GitHub topic search
- **⚠️ Security**: every vulnerability CISA added to its catalog of flaws exploited in the wild
  this week, plus the week's critical GitHub advisories; Claude writes up the 5 most important
  and the other exploited ones are listed in one line each

<img src="docs/assets/newsletter-preview.png" alt="Top of a newsletter issue" width="480">

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
  ports.py     Protocols: PaperSource, FeedSource, TrendingSource, RepoSearchSource, LLMClient, EmailSender, HistoryStore
  services/    keyword filter, selection rules, LLM-backed curators, dedup
  adapters/    arXiv, RSS/Atom, GitHub releases, GitHub Trending, GitHub search, GitHub advisories, CISA KEV, Claude, Resend, JSON history
  rendering/   Jinja2 templates (HTML + plain text)
  prompts/     system prompts, versioned like code
  pipeline.py  builds six independent sections, then publishes
  bootstrap.py the only place that wires concrete adapters
```

Design choices:

- **Sections fail independently.** A broken feed or a layout change on GitHub Trending
  turns one section into an "unavailable this week" notice; the email still goes out.
- **The LLM never produces URLs.** It answers with indices or IDs that are mapped back to
  source data.
- **Structured output is validated.** Claude answers with JSON constrained by the Pydantic
  model's schema; invalid output is retried once, then the batch is skipped.
- **Nothing missed on dev tools.** GitHub's release feeds are capped at 10 entries, which
  busy projects exceed with pre-releases, so releases are read through the GitHub API.
- **Exactly one email per week.** Three UTC triggers cover daylight saving time and late
  runs, a guard sends between 07:00 and 09:59 Paris, and the archive file plus a Resend
  idempotency key prevent duplicates.
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
   Actions tab to test. A manual run sends at any hour, but never twice on the same day.

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
