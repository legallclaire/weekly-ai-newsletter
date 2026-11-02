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
        "cs.LG",
        "cs.AI",
        "cs.CL",
        "stat.ML",
        "cs.IR",
        "cs.MA",
        "cs.SE",
        "cs.DC",
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
    with pytest.raises(ConfigError, match=r"settings\.yaml"):
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
