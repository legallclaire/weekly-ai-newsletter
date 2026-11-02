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
    newsletter = Newsletter(
        issue_date=date(2026, 11, 4),
        language="fr",
        news=Section.unavailable("x"),
        devtools=Section.unavailable("x"),
        papers=Section.unavailable("x"),
        repos=Section.unavailable("x"),
        extensions=Section.unavailable("x"),
    )
    assert newsletter.all_unavailable
    assert list(newsletter.sections) == ["news", "devtools", "papers", "repos", "extensions"]


def test_history_records_and_checks_with_cutoff() -> None:
    history = History()
    history.record(HistoryKind.REPO, ["acme/agent-kit"], date(2026, 9, 1))
    assert history.was_sent(HistoryKind.REPO, "acme/agent-kit")
    assert not history.was_sent(HistoryKind.REPO, "acme/agent-kit", on_or_after=date(2026, 10, 1))
    assert not history.was_sent(HistoryKind.NEWS, "acme/agent-kit")
