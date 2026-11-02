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
    secondary_tools: list[str] = Field(default_factory=list)


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
    github_token: SecretStr | None = None  # optional: raises GitHub API rate limits

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
        github_token = SecretStr(env["GITHUB_TOKEN"]) if env.get("GITHUB_TOKEN") else None
        return cls(
            anthropic_api_key=SecretStr(env["ANTHROPIC_API_KEY"]),
            email=email,
            github_token=github_token,
        )


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
