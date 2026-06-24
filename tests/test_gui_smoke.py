from __future__ import annotations

import os

# pytest-qt creates QApplication before the test body runs, so this must be set
# while the module is imported, not inside the test function.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QListWidget, QMainWindow, QSplitter, QTextBrowser, QToolBar, QWidget

from mercury_gui import Article, Feed, MercuryMainWindow



class StubFeedService:
    def __init__(self) -> None:
        self.feeds = [
            Feed("All Feeds", "internal://all", 2),
            Feed("Starred", "internal://starred", 1),
            Feed("Engineering", "https://example.test/rss.xml", 2),
        ]
        self.articles = [
            Article(
                title="First macOS article",
                feed_title="Engineering",
                author="Alice",
                published="2026-06-04 09:00",
                url="https://example.test/first",
                summary="A first summary for smoke testing.",
                markdown="First paragraph.\n\nSecond paragraph.",
                tags=("macOS", "Qt"),
                starred=True,
            ),
            Article(
                title="Second article",
                feed_title="Engineering",
                author="Bob",
                published="2026-06-04 10:00",
                url="https://example.test/second",
                summary="A second summary.",
                markdown="Second body.",
                tags=("RSS",),
                starred=False,
            ),
        ]

    def list_feeds(self) -> list[Feed]:
        return list(self.feeds)

    def list_articles(self, feed_title: str | None = None, unread_only: bool = False) -> list[Article]:
        if feed_title in (None, "All Feeds", "Engineering"):
            articles = list(self.articles)
        if feed_title == "Starred":
            articles = [article for article in self.articles if article.starred]
        elif feed_title not in (None, "All Feeds", "Engineering"):
            articles = []
        if unread_only:
            articles = [article for article in articles if article.unread]
        return articles

    def list_articles_by_tag(self, tag: str, unread_only: bool = False) -> list[Article]:
        articles = [article for article in self.articles if tag in article.tags]
        if unread_only:
            articles = [article for article in articles if article.unread]
        return articles

    def list_tags(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for article in self.articles:
            for tag in article.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items())

    def add_feed(self, url: str) -> None:
        raise AssertionError(f"unexpected add_feed call: {url}")

    def import_opml(self, path: str) -> None:
        raise AssertionError(f"unexpected import_opml call: {path}")

    def refresh_all(self) -> None:
        raise AssertionError("unexpected refresh_all call")


class StubReaderPipeline:
    def render_article_html(self, article: Article) -> str:
        return f"<h1>{article.title}</h1><p>{article.markdown}</p>"

    def clean_current_article(self, article: Article) -> str:
        return f"cleaned:{article.title}"


class StubSummaryAgent:
    def summarize(self, article: Article) -> str:
        return f"summary:{article.title}"


class StubTranslationAgent:
    def translate(self, article: Article, target_language: str = "zh-CN") -> str:
        return f"translation:{target_language}:{article.title}"


def build_window() -> MercuryMainWindow:
    return MercuryMainWindow(
        feed_service=StubFeedService(),
        reader_pipeline=StubReaderPipeline(),
        summary_agent=StubSummaryAgent(),
        translation_agent=StubTranslationAgent(),
    )


def test_main_window_builds_three_panel_shell(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible, timeout=2000)

    assert isinstance(window, QMainWindow)
    assert window.windowTitle() == "Lumen"
    assert window.findChild(QToolBar, "TopToolbar") is not None
    assert window.findChild(QSplitter, "MainSplitter") is not None
    assert window.findChild(QWidget, "Sidebar") is not None
    assert window.findChild(QWidget, "ArticlePanel") is not None
    assert window.findChild(QWidget, "ReaderPanel") is not None
    assert window.findChild(QTextBrowser, "Reader") is not None
    assert window.statusBar() is not None


def test_main_window_loads_feeds_articles_and_reader_content(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    feed_list = window.findChild(QListWidget, "FeedList")
    article_list = window.findChild(QListWidget, "ArticleList")
    reader = window.findChild(QTextBrowser, "Reader")

    assert feed_list is not None
    assert article_list is not None
    assert reader is not None
    assert feed_list.count() == 3
    assert article_list.count() == 1
    assert "First macOS article" in reader.toPlainText()
    assert window.current_article is not None
    assert window.current_article.title == "First macOS article"

    feed_list.setCurrentRow(0)

    assert article_list.count() == 2
    assert "First macOS article" in reader.toPlainText()


def test_main_window_search_filters_visible_article_rows(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    feed_list = window.findChild(QListWidget, "FeedList")
    article_list = window.findChild(QListWidget, "ArticleList")
    assert feed_list is not None
    assert article_list is not None

    feed_list.setCurrentRow(0)
    window.search_box.setText("second")

    assert article_list.item(0).isHidden()
    assert not article_list.item(1).isHidden()

    window.search_box.clear()

    assert not article_list.item(0).isHidden()
    assert not article_list.item(1).isHidden()
