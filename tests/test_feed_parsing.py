from __future__ import annotations

from mercury.feed import parse_feed_xml, parse_opml



def test_parse_rss_uses_guid_as_stable_id() -> None:
    title, articles = parse_feed_xml(
        """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <title>Example RSS</title>
            <item>
              <guid isPermaLink="false">rss-entry-1</guid>
              <title>Hello RSS</title>
              <link>/posts/hello</link>
              <description><![CDATA[<p>Body</p>]]></description>
              <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>""",
        source_url="https://example.test/feed.xml",
    )

    assert title == "Example RSS"
    assert articles[0].stable_id == "rss-entry-1"
    assert articles[0].url == "https://example.test/posts/hello"
    assert articles[0].tags == ("RSS",)


def test_parse_atom_uses_id_as_stable_id() -> None:
    title, articles = parse_feed_xml(
        """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Example Atom</title>
          <entry>
            <id>tag:example.test,2026:entry-1</id>
            <title>Hello Atom</title>
            <link href="/posts/atom" rel="alternate"/>
            <updated>2026-06-01T10:00:00Z</updated>
            <summary>Atom body</summary>
          </entry>
        </feed>""",
        source_url="https://example.test/atom.xml",
    )

    assert title == "Example Atom"
    assert articles[0].stable_id == "tag:example.test,2026:entry-1"
    assert articles[0].url == "https://example.test/posts/atom"
    assert articles[0].tags == ("Atom",)


def test_parse_opml_filters_invalid_and_duplicate_urls() -> None:
    subscriptions = parse_opml(
        """<?xml version="1.0"?>
        <opml version="2.0">
          <body>
            <outline text="Valid" xmlUrl="https://example.test/rss.xml"/>
            <outline text="Duplicate" xmlUrl="https://example.test/rss.xml"/>
            <outline text="Invalid" xmlUrl="not-a-url"/>
            <outline text="Group">
              <outline title="Nested" xmlUrl="https://nested.test/feed.xml"/>
            </outline>
          </body>
        </opml>"""
    )

    assert [(item.title, item.url) for item in subscriptions] == [
        ("Valid", "https://example.test/rss.xml"),
        ("Nested", "https://nested.test/feed.xml"),
    ]
