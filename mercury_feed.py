"""Feed / OPML service for the Mercury PySide6 prototype.

This module is intentionally independent from the GUI. It exposes the same
methods that `mercury_gui.FeedService` expects, so the GUI can swap mock data
for this implementation without knowing RSS/OPML details.
"""

from __future__ import annotations

import json
import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx


APP_DIR = Path.home() / ".mercury_pyqt"
FEED_CACHE = APP_DIR / "feed_cache.json"


@dataclass(frozen=True)
class Feed:
    """Feed metadata consumed by the GUI sidebar."""

    title: str
    url: str
    unread_count: int = 0


@dataclass(frozen=True)
class Article:
    """Article DTO consumed by the GUI reader/list panes."""

    title: str
    feed_title: str
    author: str
    published: str
    url: str
    summary: str
    markdown: str
    tags: tuple[str, ...] = ()
    starred: bool = False
    unread: bool = True


@dataclass
class FeedSubscription:
    """Persistent feed subscription record."""

    title: str
    url: str


class FeedParseError(RuntimeError):
    """Raised when an RSS/Atom document cannot be parsed."""


class LocalFeedService:
    """RSS / Atom / OPML implementation for the current GUI prototype.

    Current storage is a small JSON cache so Feed work can be tested before the
    SQLite StorageService is ready. The later StorageService can replace
    `_load_cache` and `_save_cache` while preserving the public interface.
    """

    def __init__(self, cache_path: Path = FEED_CACHE) -> None:
        self.cache_path = cache_path
        self.subscriptions: list[FeedSubscription] = []
        self.articles: list[Article] = []
        self.last_error: str | None = None
        self._load_cache()

    def list_feeds(self) -> list[Feed]:
        feeds = [
            Feed("All Feeds", "internal://all", self._unread_count(self.articles)),
            Feed("Starred", "internal://starred", len([a for a in self.articles if a.starred])),
        ]
        for subscription in self.subscriptions:
            count = self._unread_count(self._articles_for_feed(subscription.title))
            feeds.append(Feed(subscription.title, subscription.url, count))
        return feeds

    def list_articles(self, feed_title: str | None = None) -> list[Article]:
        if feed_title in (None, "All Feeds"):
            return list(self.articles)
        if feed_title == "Starred":
            return [article for article in self.articles if article.starred]
        return self._articles_for_feed(feed_title)

    def add_feed(self, url: str) -> None:
        normalized_url = self._validate_feed_url(url)
        if any(feed.url == normalized_url for feed in self.subscriptions):
            return

        feed_title, articles = self._fetch_and_parse_feed(normalized_url)
        self.subscriptions.append(FeedSubscription(feed_title, normalized_url))
        self._merge_articles(articles)
        self._save_cache()

    def import_opml(self, path: str) -> None:
        imported = parse_opml(Path(path).read_text(encoding="utf-8"))
        for subscription in imported:
            if not any(feed.url == subscription.url for feed in self.subscriptions):
                self.subscriptions.append(subscription)
        self._save_cache()

    def refresh_all(self) -> None:
        self.last_error = None
        refreshed: list[Article] = []
        errors: list[str] = []
        updated_titles: dict[str, str] = {}

        for subscription in self.subscriptions:
            try:
                title, articles = self._fetch_and_parse_feed(subscription.url)
                updated_titles[subscription.url] = title
                refreshed.extend(articles)
            except Exception as exc:  # Keep one bad feed from breaking all sync.
                errors.append(f"{subscription.url}: {exc}")

        if updated_titles:
            self.subscriptions = [
                FeedSubscription(updated_titles.get(item.url, item.title), item.url)
                for item in self.subscriptions
            ]

        self._merge_articles(refreshed)
        self.last_error = "\n".join(errors) if errors else None
        self._save_cache()

    def _fetch_and_parse_feed(self, url: str) -> tuple[str, list[Article]]:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=12.0,
            headers={"User-Agent": "MercuryPyQt/0.1 (+local-first RSS reader)"},
        )
        response.raise_for_status()
        source_url = str(response.url)
        try:
            return parse_feed_xml(response.text, source_url=source_url)
        except FeedParseError:
            discovered_url = discover_feed_url(response.text, source_url)
            if not discovered_url or discovered_url == source_url:
                raise

            discovered_response = httpx.get(
                discovered_url,
                follow_redirects=True,
                timeout=12.0,
                headers={"User-Agent": "MercuryPyQt/0.1 (+local-first RSS reader)"},
            )
            discovered_response.raise_for_status()
            return parse_feed_xml(discovered_response.text, source_url=str(discovered_response.url))

    def _merge_articles(self, incoming: Iterable[Article]) -> None:
        by_key = {article_key(article): article for article in self.articles}
        for article in incoming:
            by_key[article_key(article)] = article
        self.articles = sorted(by_key.values(), key=lambda item: item.published, reverse=True)

    def _articles_for_feed(self, feed_title: str) -> list[Article]:
        return [article for article in self.articles if article.feed_title == feed_title]

    @staticmethod
    def _unread_count(articles: Iterable[Article]) -> int:
        return len([article for article in articles if article.unread])

    @staticmethod
    def _validate_feed_url(url: str) -> str:
        normalized = url.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("请输入有效的 http(s) Feed URL。")
        return normalized

    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.subscriptions = [FeedSubscription(**item) for item in data.get("subscriptions", [])]
        self.articles = [
            Article(**{**item, "tags": tuple(item.get("tags", []))})
            for item in data.get("articles", [])
        ]

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "subscriptions": [asdict(item) for item in self.subscriptions],
            "articles": [asdict(item) for item in self.articles],
        }
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_opml(xml_text: str) -> list[FeedSubscription]:
    """Parse OPML subscriptions using Python's standard XML library."""
    root = ET.fromstring(_clean_xml_text(xml_text))
    feeds: list[FeedSubscription] = []
    for outline in root.findall(".//outline"):
        url = outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl")
        if not url:
            continue
        title = outline.attrib.get("title") or outline.attrib.get("text") or url
        feeds.append(FeedSubscription(title=title.strip(), url=url.strip()))
    return feeds


def parse_feed_xml(xml_text: str, source_url: str = "") -> tuple[str, list[Article]]:
    """Parse a minimal RSS or Atom document.

    This stdlib parser is enough for MVP tests and avoids blocking the team on
    installing `feedparser`. It can be replaced by feedparser later behind the
    same `LocalFeedService` interface.
    """
    cleaned_xml = _clean_xml_text(xml_text)
    try:
        root = ET.fromstring(cleaned_xml)
    except ET.ParseError as exc:
        if looks_like_html(cleaned_xml):
            raise FeedParseError(
                "这个地址返回的是网页 HTML，不是 RSS/Atom Feed。"
                "请输入直接的订阅源地址，或使用带 RSS/Atom 链接的网站首页让程序自动发现。"
            ) from exc
        raise FeedParseError(
            "这个地址返回的内容不是规范 RSS/Atom XML，解析失败。"
            f"原始错误：{exc}。"
        ) from exc
    if _local_name(root.tag) == "rss":
        return _parse_rss(root, source_url)
    if _local_name(root.tag) == "feed":
        return _parse_atom(root, source_url)
    raise FeedParseError("不支持的 Feed 格式：只支持 RSS 或 Atom。")


def discover_feed_url(html_text: str, page_url: str) -> str | None:
    """Find RSS/Atom link tags in a normal website page.

    This is a lightweight discovery helper for MVP. A fuller implementation can
    later use BeautifulSoup, but regex is enough for common `<link>` feed tags.
    """
    if not looks_like_html(html_text):
        return None
    link_tags = re.findall(r"<link\b[^>]*>", html_text, flags=re.IGNORECASE)
    for tag in link_tags:
        rel = _html_attr(tag, "rel").lower()
        feed_type = _html_attr(tag, "type").lower()
        href = _html_attr(tag, "href")
        if not href:
            continue
        is_feed = (
            "alternate" in rel
            and feed_type in {"application/rss+xml", "application/atom+xml", "application/feed+json"}
        )
        if is_feed:
            return urljoin(page_url, html.unescape(href))
    return None


def looks_like_html(text: str) -> bool:
    prefix = text[:1000].lower()
    return "<html" in prefix or "<!doctype html" in prefix or "<head" in prefix


def _html_attr(tag: str, attr: str) -> str:
    match = re.search(rf"""{attr}\s*=\s*["']([^"']+)["']""", tag, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _clean_xml_text(text: str) -> str:
    """Remove characters that XML 1.0 parsers reject.

    Some real feeds contain invisible control characters. Removing them makes
    the MVP parser more tolerant without changing valid RSS/Atom semantics.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    return "".join(char for char in text if _is_valid_xml_char(char))


def _is_valid_xml_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        codepoint == 0x09
        or codepoint == 0x0A
        or codepoint == 0x0D
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _parse_rss(root: ET.Element, source_url: str) -> tuple[str, list[Article]]:
    channel = root.find("channel")
    if channel is None:
        raise FeedParseError("RSS 缺少 channel。")
    feed_title = _text(channel, "title") or _host_title(source_url)
    articles = []
    for item in channel.findall("item"):
        title = _text(item, "title") or "Untitled"
        link = _text(item, "link") or source_url
        summary = _text(item, "description")
        published = _format_date(_text(item, "pubDate"))
        author = _text(item, "author") or _text(item, "creator") or feed_title
        markdown = html.unescape(_strip_html(summary or title))
        articles.append(
            Article(
                title=html.unescape(title.strip()),
                feed_title=feed_title,
                author=html.unescape(author.strip()),
                published=published,
                url=link.strip(),
                summary=html.unescape(_strip_html(summary)) if summary else "",
                markdown=markdown,
                tags=("RSS",),
            )
        )
    return feed_title, articles


def _parse_atom(root: ET.Element, source_url: str) -> tuple[str, list[Article]]:
    feed_title = _child_text(root, "title") or _host_title(source_url)
    articles = []
    for entry in _children(root, "entry"):
        title = _child_text(entry, "title") or "Untitled"
        link = _atom_link(entry) or source_url
        summary = _child_text(entry, "summary") or _child_text(entry, "content")
        published = _format_date(_child_text(entry, "published") or _child_text(entry, "updated"))
        author = _atom_author(entry) or feed_title
        markdown = html.unescape(_strip_html(summary or title))
        articles.append(
            Article(
                title=html.unescape(title.strip()),
                feed_title=feed_title,
                author=html.unescape(author.strip()),
                published=published,
                url=link.strip(),
                summary=html.unescape(_strip_html(summary)) if summary else "",
                markdown=markdown,
                tags=("Atom",),
            )
        )
    return feed_title, articles


def article_key(article: Article) -> str:
    return article.url or f"{article.feed_title}:{article.title}:{article.published}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(parent) if _local_name(child.tag) == name]


def _child_text(parent: ET.Element, name: str) -> str:
    for child in _children(parent, name):
        return "".join(child.itertext()).strip()
    return ""


def _text(parent: ET.Element, tag_name: str) -> str:
    child = parent.find(tag_name)
    if child is not None and child.text:
        return child.text.strip()
    for item in list(parent):
        if _local_name(item.tag) == tag_name.lower():
            return "".join(item.itertext()).strip()
    return ""


def _atom_link(entry: ET.Element) -> str:
    for child in _children(entry, "link"):
        rel = child.attrib.get("rel", "alternate")
        href = child.attrib.get("href")
        if href and rel == "alternate":
            return href
    for child in _children(entry, "link"):
        href = child.attrib.get("href")
        if href:
            return href
    return ""


def _atom_author(entry: ET.Element) -> str:
    for author in _children(entry, "author"):
        name = _child_text(author, "name")
        if name:
            return name
    return ""


def _format_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


def _host_title(url: str) -> str:
    host = urlparse(url).netloc
    return host or "Untitled Feed"


def _strip_html(value: str) -> str:
    output: list[str] = []
    in_tag = False
    for char in value or "":
        if char == "<":
            in_tag = True
            continue
        if char == ">":
            in_tag = False
            continue
        if not in_tag:
            output.append(char)
    return " ".join("".join(output).split())
