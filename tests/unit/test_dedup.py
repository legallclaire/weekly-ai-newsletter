from datetime import date

from tests.factories import make_feed_item, make_repo
from weekly_ai_newsletter.domain.history import History, HistoryKind
from weekly_ai_newsletter.services.dedup import drop_sent, unique_by


def test_unique_by_keeps_first_occurrence_in_order() -> None:
    items = [
        make_feed_item("u1", source="A"),
        make_feed_item("u2"),
        make_feed_item("u1", source="B"),
    ]
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
