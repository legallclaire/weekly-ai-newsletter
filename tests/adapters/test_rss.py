from datetime import UTC, datetime

import httpx
import pytest

from weekly_ai_newsletter.adapters.rss import RssFeedSource, html_to_text
from weekly_ai_newsletter.domain.errors import SourceError
from weekly_ai_newsletter.domain.window import TimeWindow

WINDOW = TimeWindow(datetime(2026, 10, 28, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC))

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Lab blog</title>
<item><title>New  model released</title><link>https://lab.example/new-model</link>
  <description>&lt;p&gt;We release a &lt;b&gt;new&lt;/b&gt;
    model &amp;amp; tools.&lt;/p&gt;</description>
  <pubDate>Thu, 29 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Old post</title><link>https://lab.example/old</link>
  <description>Old</description><pubDate>Mon, 05 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title>Undated post</title><link>https://lab.example/undated</link>
  <description>No date</description></item>
<item><title>No link</title><description>x</description>
  <pubDate>Thu, 29 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

RELEASES_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Release notes from claude-code</title>
<entry><id>tag:github.com,2008:Repository/1/v2.1.0</id>
  <updated>2026-10-30T18:00:00Z</updated>
  <link rel="alternate" type="text/html"
        href="https://github.com/anthropics/claude-code/releases/tag/v2.1.0"/>
  <title>v2.1.0</title>
  <content type="html">&lt;ul&gt;&lt;li&gt;Added hooks&lt;/li&gt;&lt;/ul&gt;</content></entry>
</feed>"""


def source_serving(body: str, status: int = 200) -> RssFeedSource:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    return RssFeedSource(httpx.Client(transport=transport))


def test_parses_rss_keeping_dated_linked_items_in_window() -> None:
    [item] = source_serving(RSS).fetch("Lab", "https://lab.example/feed", WINDOW)
    assert item.title == "New model released"
    assert item.url == "https://lab.example/new-model"
    assert item.summary == "We release a new model & tools."
    assert item.source == "Lab"
    assert item.published == datetime(2026, 10, 29, 9, tzinfo=UTC)


def test_parses_github_release_atom_content() -> None:
    [item] = source_serving(RELEASES_ATOM).fetch("Claude Code", "https://x", WINDOW)
    assert item.title == "v2.1.0"
    assert item.summary == "Added hooks"
    assert item.url.endswith("/releases/tag/v2.1.0")


def test_garbage_is_a_source_error() -> None:
    with pytest.raises(SourceError, match="Lab"):
        source_serving("<html>not a feed").fetch("Lab", "https://x", WINDOW)


def test_html_to_text_collapses_whitespace() -> None:
    assert html_to_text("<p>a</p>\n<p>b  c</p>") == "a b c"


def rss_item(title: str, link: str = "https://lab.example/post") -> str:
    return f"""<?xml version="1.0"?><rss version="2.0"><channel><title>Lab</title>
<item><title>{title}</title><link>{link}</link><description>x</description>
  <pubDate>Thu, 29 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>"""


def test_plain_text_titles_keep_angle_brackets() -> None:
    [item] = source_serving(rss_item("Why &lt;think&gt; tags help")).fetch(
        "Lab", "https://x", WINDOW
    )
    assert item.title == "Why <think> tags help"


def test_html_titles_are_converted_to_text() -> None:
    atom = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>1</id><published>2026-10-29T09:00:00Z</published>
  <link href="https://lab.example/post"/>
  <title type="html">&lt;b&gt;Bold&lt;/b&gt; news</title></entry></feed>"""
    [item] = source_serving(atom).fetch("Lab", "https://x", WINDOW)
    assert item.title == "Bold news"


@pytest.mark.parametrize("link", ["javascript:alert(1)", "ftp://lab.example/post"])
def test_non_web_links_are_dropped(link: str) -> None:
    assert source_serving(rss_item("Post", link)).fetch("Lab", "https://x", WINDOW) == []
