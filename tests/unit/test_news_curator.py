from tests.factories import make_feed_item
from tests.fakes import FakeLLM
from weekly_ai_newsletter.services.news_curator import NewsCurator, NewsPick, NewsSelection

ITEMS = [
    make_feed_item("https://a.example/1", title="Model X released", source="Lab A"),
    make_feed_item("https://b.example/2", title="Minor update", source="Lab B"),
]


def test_maps_picks_back_to_source_urls() -> None:
    llm = FakeLLM({NewsSelection: NewsSelection(picks=[NewsPick(index=0, summary="Big release.")])})
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
