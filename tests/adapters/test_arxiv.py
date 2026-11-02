from datetime import UTC, datetime

import httpx
import pytest

from weekly_ai_newsletter.adapters.arxiv import ArxivPaperSource
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow(datetime(2026, 10, 26, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC))


def entry(arxiv_id: str, published: str, title: str = "Agents  that\n plan") -> str:
    return f"""
    <entry>
      <id>http://arxiv.org/abs/{arxiv_id}v2</id>
      <published>{published}</published>
      <updated>{published}</updated>
      <title>{title}</title>
      <summary>  We study agents.\n  </summary>
      <author><name>Ada Lovelace</name></author>
      <author><name>Alan Turing</name></author>
      <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
      <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    </entry>"""


def atom(*entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>"
    )


def test_fetches_pages_until_short_page_and_filters_window() -> None:
    pages = {
        "0": atom(
            entry("2610.00001", "2026-10-28T10:00:00Z"),
            entry("2610.00002", "2026-10-29T10:00:00Z"),
        ),
        "2": atom(entry("2610.00003", "2026-11-02T01:00:00Z")),
    }
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=pages[request.url.params["start"]])

    delays: list[float] = []
    source = ArxivPaperSource(
        httpx.Client(transport=httpx.MockTransport(handler)), page_size=2, sleep=delays.append
    )
    papers = source.fetch(["cs.AI", "cs.LG"], WINDOW)

    assert [p.arxiv_id for p in papers] == ["2610.00001", "2610.00002"]
    assert delays == [3.0]
    query = requests[0].url.params["search_query"]
    assert "cat:cs.AI OR cat:cs.LG" in query
    assert "submittedDate:[202610260000 TO 202611020000]" in query

    paper = papers[0]
    assert paper.title == "Agents that plan"
    assert paper.abstract == "We study agents."
    assert paper.authors == ("Ada Lovelace", "Alan Turing")
    assert paper.categories == ("cs.AI", "cs.LG")
    assert paper.url == "https://arxiv.org/abs/2610.00001"
    assert paper.published == datetime(2026, 10, 28, 10, tzinfo=UTC)


def test_empty_week_returns_no_papers() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=atom())))
    assert ArxivPaperSource(client, sleep=lambda _: None).fetch(["cs.AI"], WINDOW) == []


def atom_with_total(total: int, *entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"'
        ' xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        f"<opensearch:totalResults>{total}</opensearch:totalResults>" + "".join(entries) + "</feed>"
    )


def test_truncated_page_is_retried() -> None:
    full = atom_with_total(
        2, entry("2610.00001", "2026-10-28T10:00:00Z"), entry("2610.00002", "2026-10-29T10:00:00Z")
    )
    responses = [atom_with_total(2), full]
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=responses.pop(0)))
    )
    papers = ArxivPaperSource(client, page_size=10, sleep=lambda _: None).fetch(["cs.AI"], WINDOW)
    assert [p.arxiv_id for p in papers] == ["2610.00001", "2610.00002"]


def test_persistently_truncated_results_are_a_source_error() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=atom_with_total(5)))
    )
    source = ArxivPaperSource(client, page_size=10, sleep=lambda _: None)
    with pytest.raises(SourceError, match="5"):
        source.fetch(["cs.AI"], WINDOW)
