from tests.factories import make_repo
from weekly_ai_newsletter.config import RepoKeywords
from weekly_ai_newsletter.services.repo_filter import RepoRuleFilter

FILTER = RepoRuleFilter(
    RepoKeywords(include=["llm", "agent", "ai"], exclude=["awesome", "prompts"])
)


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
