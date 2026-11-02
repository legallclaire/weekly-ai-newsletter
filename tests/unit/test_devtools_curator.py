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
    curator = DevToolsCurator(FakeLLM({DevToolsSelection: selection}), language="en")
    assert curator.curate(ITEMS) == []
