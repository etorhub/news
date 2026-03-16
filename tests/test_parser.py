"""Tests for feed parser."""



from app.feed.parser import parse_feed

RSS_MINIMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Test Feed</title>
    <item>
        <title>Article One</title>
        <link>https://example.com/1</link>
        <description>Short summary here.</description>
        <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
        <title>Article Two</title>
        <link>https://example.com/2</link>
        <description><p>HTML <b>summary</b> here.</p></description>
        <pubDate>Tue, 02 Jan 2024 14:30:00 GMT</pubDate>
    </item>
</channel>
</rss>"""


RSS_WITH_CONTENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
    <title>Full Text Feed</title>
    <item>
        <title>Full Article</title>
        <link>https://example.com/full</link>
        <description>Summary only</description>
        <content:encoded><![CDATA[<p>Full article body here.</p>]]></content:encoded>
        <pubDate>Wed, 03 Jan 2024 10:00:00 GMT</pubDate>
    </item>
</channel>
</rss>"""


RSS_MISSING_GUID = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>No Guid</title>
    <item>
        <title>No Guid Item</title>
        <link>https://example.com/no-guid</link>
    </item>
</channel>
</rss>"""


def test_parse_feed_minimal_rss() -> None:
    """Parse minimal RSS returns normalized articles."""
    articles = parse_feed(RSS_MINIMAL)
    assert len(articles) == 2
    a1, a2 = articles[0], articles[1]
    assert a1["title"] == "Article One"
    assert a1["url"] == "https://example.com/1"
    assert a1["raw_text"] == "Short summary here."
    assert a1["full_text"] == ""
    assert a1["published_at"] is not None
    assert a1["published_at"].year == 2024

    assert a2["title"] == "Article Two"
    assert a2["url"] == "https://example.com/2"
    assert "HTML" in a2["raw_text"] and "summary" in a2["raw_text"]


def test_parse_feed_with_content_encoded() -> None:
    """Parse RSS with content:encoded extracts full text."""
    articles = parse_feed(RSS_WITH_CONTENT)
    assert len(articles) == 1
    a = articles[0]
    assert a["title"] == "Full Article"
    assert "Full article body" in a["full_text"]
    assert "Summary only" in a["raw_text"]


def test_parse_feed_missing_guid_uses_link() -> None:
    """When guid is missing, url is used as fallback."""
    articles = parse_feed(RSS_MISSING_GUID)
    assert len(articles) == 1
    assert articles[0]["url"] == "https://example.com/no-guid"
    assert articles[0]["guid"] == "https://example.com/no-guid"


def test_parse_feed_skips_entries_without_url() -> None:
    """Entries without link/url are skipped."""
    rss_no_link = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>X</title>
    <item><title>No link</title></item>
    </channel></rss>"""
    articles = parse_feed(rss_no_link)
    assert len(articles) == 0


def test_parse_feed_empty_content() -> None:
    """Empty or invalid content returns empty list."""
    assert parse_feed(b"") == []
    assert parse_feed(b"<html>not a feed</html>") == []
