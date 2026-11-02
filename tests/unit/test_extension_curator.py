from tests.factories import make_extension
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.extension_curator import (
    ExtensionCurator,
    ExtensionVerdict,
    ExtensionVerdicts,
)

MCP = ("mcp-server",)


def keep_all(names: list[str]) -> FakeLLM:
    return FakeLLM(
        {
            ExtensionVerdicts: ExtensionVerdicts(
                verdicts=[
                    ExtensionVerdict(full_name=n, keep=True, why_interesting=f"Why {n}.")
                    for n in names
                ]
            )
        }
    )


def curator(llm: FakeLLM, **kwargs: int) -> ExtensionCurator:
    return ExtensionCurator(
        llm,
        language="fr",
        max_items=kwargs.get("max_items", 5),
        max_mcp=kwargs.get("max_mcp", 2),
        mcp_topics=MCP,
    )


def test_keeps_best_starred_and_caps_mcp_servers() -> None:
    repos = [
        make_extension("m/one", stars=900, topics=MCP),
        make_extension("m/two", stars=800, topics=MCP),
        make_extension("m/three", stars=700, topics=MCP),
        make_extension("s/skill", stars=100),
    ]
    kept = curator(keep_all([r.full_name for r in repos])).curate(repos)
    assert [k.repo.full_name for k in kept] == ["m/one", "m/two", "s/skill"]
    assert kept[0].why_interesting == "Why m/one."
    assert kept[0].is_mcp and not kept[2].is_mcp


def test_rejected_unknown_and_duplicate_verdicts_are_ignored() -> None:
    repos = [make_extension("s/a"), make_extension("s/b")]
    llm = FakeLLM(
        {
            ExtensionVerdicts: ExtensionVerdicts(
                verdicts=[
                    ExtensionVerdict(full_name="s/a", keep=False, why_interesting=""),
                    ExtensionVerdict(full_name="ghost/x", keep=True, why_interesting="?"),
                    ExtensionVerdict(full_name="s/b", keep=True, why_interesting="B."),
                    ExtensionVerdict(full_name="s/b", keep=True, why_interesting="B again."),
                ]
            )
        }
    )
    kept = curator(llm).curate(repos)
    assert [(k.repo.full_name, k.why_interesting) for k in kept] == [("s/b", "B.")]


def test_respects_max_items_and_skips_llm_when_empty() -> None:
    repos = [make_extension(f"s/{n}", stars=100 - n) for n in range(4)]
    assert len(curator(keep_all([r.full_name for r in repos]), max_items=2).curate(repos)) == 2
    llm = FakeLLM({})
    assert curator(llm).curate([]) == []
    assert llm.calls == []
