from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


import httpx
import pytest

import mercury_feed
from mercury_feed import (
    FeedParseError,
    FeedSubscription,
    LocalFeedService,
    discover_feed_url,
    parse_feed_xml,
    parse_opml,
)


RSS_XML = """<?xml version='1.0' encoding='UTF-8'?>
<rss version="2.0">
  <channel>
    <title>Reliable RSS</title>
    <link>https://example.test/</link>
    <item>
      <title>RSS Article 1</title>
      <link>https://example.test/article-1</link>
      <guid>article-1</guid>
      <pubDate>Mon, 03 Jun 2024 12:00:00 +0000</pubDate>
      <description><![CDATA[<p>Summary <strong>text</strong></p>]]></description>
      <author>Author One</author>
    </item>
  </channel>
</rss>
"""


ATOM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Reliable Atom</title>
  <entry>
    <title>Atom Article 1</title>
    <link href="https://example.test/atom-1" rel="alternate" />
    <id>atom-1</id>
    <updated>2024-06-03T12:00:00Z</updated>
    <summary>Atom summary</summary>
    <author><name>Author Atom</name></author>
  </entry>
</feed>
"""


OPML_XML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Subscriptions</title></head>
  <body>
    <outline text="Blog One" xmlUrl="https://blog.one/feed.xml" />
    <outline title="Blog Two" xmlUrl="https://blog.two/rss" />
    <outline text="Folder">
      <outline title="Nested Blog" xmlUrl="https://nested.example/rss" />
    </outline>
  </body>
</opml>
"""


HTML_WITH_FEED_LINK = """<!doctype html>
<html>
  <head>
    <link rel="alternate" type="application/rss+xml" href="/rss.xml">
  </head>
  <body>Home page</body>
</html>
"""


def make_http_get(responses: dict[str, httpx.Response]) -> Callable[..., httpx.Response]:
    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        response = responses[url]
        if response.request is None:
            return httpx.Response(
                response.status_code,
                text=response.text,
                headers=response.headers,
                request=httpx.Request("GET", url),
            )
        return response

    return fake_get


def test_parse_rss_feed_xml_normalizes_article_fields() -> None:
    feed_title, entries = parse_feed_xml(RSS_XML, source_url="https://example.test/rss.xml")

    assert feed_title == "Reliable RSS"
    assert len(entries) == 1
    assert entries[0].title == "RSS Article 1"
    assert entries[0].url == "https://example.test/article-1"
    assert entries[0].author == "Author One"
    assert entries[0].published == "2024-06-03 12:00"
    assert entries[0].summary == "Summary text"
    assert entries[0].markdown == "Summary text"
    assert entries[0].tags == ("RSS",)


def test_parse_atom_feed_xml_normalizes_article_fields() -> None:
    feed_title, entries = parse_feed_xml(ATOM_XML, source_url="https://example.test/atom.xml")

    assert feed_title == "Reliable Atom"
    assert len(entries) == 1
    assert entries[0].title == "Atom Article 1"
    assert entries[0].url == "https://example.test/atom-1"
    assert entries[0].author == "Author Atom"
    assert entries[0].published == "2024-06-03 12:00"
    assert entries[0].summary == "Atom summary"
    assert entries[0].tags == ("Atom",)


def test_parse_opml_reads_nested_outline_subscriptions() -> None:
    subscriptions = parse_opml(OPML_XML)

    assert subscriptions == [
        FeedSubscription(title="Blog One", url="https://blog.one/feed.xml"),
        FeedSubscription(title="Blog Two", url="https://blog.two/rss"),
        FeedSubscription(title="Nested Blog", url="https://nested.example/rss"),
    ]


def test_discover_feed_url_resolves_relative_rss_link() -> None:
    assert discover_feed_url(HTML_WITH_FEED_LINK, "https://example.test/blog/") == (
        "https://example.test/rss.xml"
    )


def test_parse_feed_xml_rejects_xml_shaped_html_without_feed_document() -> None:
    with pytest.raises(FeedParseError, match="不支持的 Feed 格式"):
        parse_feed_xml("<html><body>not a feed</body></html>", source_url="https://example.test")


def test_parse_feed_xml_reports_malformed_html_response() -> None:
    with pytest.raises(FeedParseError, match="网页 HTML"):
        parse_feed_xml("<!doctype html><html><body>not closed", source_url="https://example.test")


def test_local_feed_service_add_feed_persists_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "feed_cache.json"
    service = LocalFeedService(cache_path=cache_path)
    monkeypatch.setattr(
        mercury_feed.httpx,
        "get",
        make_http_get(
            {
                "https://example.test/rss.xml": httpx.Response(
                    200,
                    text=RSS_XML,
                    request=httpx.Request("GET", "https://example.test/rss.xml"),
                )
            }
        ),
    )

    service.add_feed(" https://example.test/rss.xml ")

    assert service.subscriptions == [
        FeedSubscription(title="Reliable RSS", url="https://example.test/rss.xml")
    ]
    assert [article.title for article in service.articles] == ["RSS Article 1"]
    assert json.loads(cache_path.read_text(encoding="utf-8"))["subscriptions"] == [
        {"title": "Reliable RSS", "url": "https://example.test/rss.xml"}
    ]


def test_local_feed_service_add_feed_discovers_feed_from_html_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "feed_cache.json"
    service = LocalFeedService(cache_path=cache_path)
    monkeypatch.setattr(
        mercury_feed.httpx,
        "get",
        make_http_get(
            {
                "https://example.test/blog": httpx.Response(
                    200,
                    text=HTML_WITH_FEED_LINK,
                    request=httpx.Request("GET", "https://example.test/blog"),
                ),
                "https://example.test/rss.xml": httpx.Response(
                    200,
                    text=RSS_XML,
                    request=httpx.Request("GET", "https://example.test/rss.xml"),
                ),
            }
        ),
    )

    service.add_feed("https://example.test/blog")

    assert service.subscriptions == [
        FeedSubscription(title="Reliable RSS", url="https://example.test/blog")
    ]
    assert [article.url for article in service.articles] == ["https://example.test/article-1"]


def test_local_feed_service_refresh_all_records_per_feed_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "feed_cache.json"
    service = LocalFeedService(cache_path=cache_path)
    service.subscriptions = [
        FeedSubscription(title="Good Feed", url="https://example.test/rss.xml"),
        FeedSubscription(title="Bad Feed", url="https://example.test/error.xml"),
    ]
    monkeypatch.setattr(
        mercury_feed.httpx,
        "get",
        make_http_get(
            {
                "https://example.test/rss.xml": httpx.Response(
                    200,
                    text=RSS_XML,
                    request=httpx.Request("GET", "https://example.test/rss.xml"),
                ),
                "https://example.test/error.xml": httpx.Response(
                    500,
                    text="Server error",
                    request=httpx.Request("GET", "https://example.test/error.xml"),
                ),
            }
        ),
    )

    service.refresh_all()

    assert "https://example.test/error.xml" in service.last_error
    assert service.subscriptions[0].title == "Reliable RSS"
    assert service.subscriptions[1].title == "Bad Feed"
    assert [article.title for article in service.articles] == ["RSS Article 1"]


def test_local_feed_service_rejects_invalid_feed_url(tmp_path: Path) -> None:
    service = LocalFeedService(cache_path=tmp_path / "feed_cache.json")

    with pytest.raises(ValueError, match="http"):
        service.add_feed("file:///tmp/feed.xml")

    assert service.subscriptions == []
    assert service.articles == []
