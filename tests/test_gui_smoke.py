from __future__ import annotations

import os

# pytest-qt creates QApplication before the test body runs, so this must be set
# while the module is imported, not inside the test function.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MERCURY_READER_RENDERER", "text")

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QToolBar,
    QWidget,
)

import mercury.gui as gui_module
from mercury.gui import Article, Feed, MercuryMainWindow
from mercury.agent.translation.translation_agent import (
    TranslationRequest,
    TranslationResult,
    TranslationSegment,
)



class StubFeedService:
    def __init__(self) -> None:
        self.deleted_feed_batches: list[list[str]] = []
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

    def delete_feeds(self, feed_titles: list[str]) -> None:
        self.deleted_feed_batches.append(list(feed_titles))
        self.feeds = [feed for feed in self.feeds if feed.title not in feed_titles]

    def set_article_unread(self, entry_id: str, unread: bool) -> None:
        self.articles = [
            Article(
                title=article.title,
                feed_title=article.feed_title,
                author=article.author,
                published=article.published,
                url=article.url,
                summary=article.summary,
                markdown=article.markdown,
                stable_id=article.stable_id,
                entry_id=article.entry_id,
                tags=article.tags,
                starred=article.starred,
                unread=unread if article.entry_id == entry_id else article.unread,
            )
            for article in self.articles
        ]


class StubReaderPipeline:
    def render_article_html(self, article: Article) -> str:
        return f"<h1>{article.title}</h1><p>{article.markdown}</p>"

    def clean_current_article(self, article: Article) -> str:
        return f"cleaned:{article.title}"


class StubSummaryAgent:
    def summarize(self, article: Article) -> str:
        return f"summary:{article.title}"


class StubTranslationAgent:
    class _Template:
        fingerprint = "stubfp"

    template = _Template()

    def build_model_id(self) -> str:
        return "stub-model@stubfp"

    def run(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            entry_id=request.entry_id,
            target_language=request.target_language,
            segments=(
                TranslationSegment(
                    source_text=request.content,
                    trans_text=f"translation:{request.target_language}:{request.content}",
                    source_hash="stubhash",
                    position=0,
                ),
            ),
            model_id=self.build_model_id(),
            template_fingerprint=self.template.fingerprint,
        )


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


def test_reader_source_link_stays_inside_app(qtbot, monkeypatch) -> None:
    opened_urls = []

    def fake_open_url(url: QUrl) -> bool:
        opened_urls.append(url.toString())
        return True

    monkeypatch.setattr(gui_module.QDesktopServices, "openUrl", fake_open_url)

    window = build_window()
    qtbot.addWidget(window)
    loaded_urls = []

    class FakeInternalBrowser(QWidget):
        def load(self, url: QUrl) -> None:
            loaded_urls.append(url.toString())

    window.reader = FakeInternalBrowser()
    window._open_reader_source_url(QUrl("https://example.test/article"))

    assert opened_urls == []
    assert loaded_urls == ["https://example.test/article"]
    assert not window.reader_nav.isHidden()
    assert window.original_source_url == "https://example.test/article"
    assert "正在打开原文" in window.summary_text.text()


def test_agent_panels_can_be_resized_compactly(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    assert window.summary_panel.minimumHeight() <= 32
    assert window.translation_panel.minimumHeight() <= 32
    assert window.summary_panel_frame.minimumHeight() <= 64
    assert window.translation_panel_frame.minimumHeight() <= 64
    assert window.agent_panel_splitter.childrenCollapsible()
    assert window.agent_panel_splitter.isCollapsible(0)
    assert window.agent_panel_splitter.isCollapsible(1)


def test_more_filters_menu_replaces_placeholder_dialog(qtbot, monkeypatch) -> None:
    window = build_window()
    qtbot.addWidget(window)
    shown_dialogs = []

    def fake_dialog(*args, **kwargs) -> None:
        shown_dialogs.append((args, kwargs))

    monkeypatch.setattr(window, "_show_interface_dialog", fake_dialog)

    menu = window._build_more_filters_menu()

    assert shown_dialogs == []
    assert [action.text() for action in menu.actions()] == ["显示全部", "只看未读", "只看星标", "清除搜索"]


def test_agent_panels_collapse_when_both_closed(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    qtbot.waitUntil(window.isVisible, timeout=2000)

    window._render_summary_panel("summary")
    window._auto_expand_agent_panel()
    window._render_translation_panel("translation")
    window._auto_expand_agent_panel()

    assert window.summary_panel_expanded
    assert window.agent_panel_splitter.isVisible()

    window.on_close_summary_panel()
    assert window.summary_panel_expanded

    window.on_close_translation_panel()

    assert not window.summary_panel_expanded
    assert not window.agent_panel_splitter.isVisible()
    assert window.vertical_splitter.sizes()[1] <= 70


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


def test_unread_filter_keeps_tag_mode(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    window.on_tag_tab()
    tag_item = window.feed_list.findItems("macOS (1)", Qt.MatchExactly)[0]
    window.feed_list.setCurrentItem(tag_item)

    assert window.current_sidebar_mode == "tags"
    assert window.current_tag == "macOS"

    window.unread_filter_btn.setChecked(True)
    window.on_unread_filter()

    assert window.current_sidebar_mode == "tags"
    assert window.current_tag == "macOS"
    assert window.current_feed_title is None
    assert window.article_scope_label.text() == "Tag: macOS · 未读"


def test_unread_filter_keeps_tag_mode_after_auto_mark_read(qtbot) -> None:
    service = StubFeedService()
    first = service.articles[0]
    service.articles[0] = Article(
        title=first.title,
        feed_title=first.feed_title,
        author=first.author,
        published=first.published,
        url=first.url,
        summary=first.summary,
        markdown=first.markdown,
        stable_id=first.stable_id,
        entry_id="entry-first",
        tags=first.tags,
        starred=first.starred,
        unread=True,
    )
    window = MercuryMainWindow(
        feed_service=service,
        reader_pipeline=StubReaderPipeline(),
        summary_agent=StubSummaryAgent(),
        translation_agent=StubTranslationAgent(),
    )
    qtbot.addWidget(window)

    window.on_tag_tab()
    tag_item = window.feed_list.findItems("macOS (1)", Qt.MatchExactly)[0]
    window.feed_list.setCurrentItem(tag_item)
    window.unread_filter_btn.setChecked(True)
    window.on_unread_filter()

    assert window.current_sidebar_mode == "tags"
    assert window.current_tag == "macOS"
    assert window.current_feed_title is None
    assert window.sidebar_title.text() == "Tags"


def test_reader_original_status_updates_on_load_and_back(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    window._enter_reader_original_mode(QUrl("https://example.test/first"))
    window._on_reader_load_finished(True)

    assert "已打开原文" in window.summary_text.text()

    window.on_reader_back()

    assert "已打开：First macOS article" in window.summary_text.text()


def test_feed_checkboxes_only_show_in_batch_selection_mode(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    engineering_item = window.feed_list.item(2)
    assert not engineering_item.flags() & Qt.ItemIsUserCheckable
    assert window.batch_delete_feed_action.text() == "批量选择"

    window.on_batch_delete_feeds()

    engineering_item = window.feed_list.item(2)
    assert engineering_item.flags() & Qt.ItemIsUserCheckable
    assert window.batch_delete_feed_action.text() == "删除已选"
    assert window.cancel_batch_delete_feed_action.isVisible()

    window.on_cancel_batch_delete_feeds()

    engineering_item = window.feed_list.item(2)
    assert not engineering_item.flags() & Qt.ItemIsUserCheckable
    assert window.batch_delete_feed_action.text() == "批量选择"
    assert not window.cancel_batch_delete_feed_action.isVisible()


def test_translate_button_runs_translation_worker(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)
    window.show()

    window.on_translate()

    qtbot.waitUntil(
        lambda: "翻译完成" in window.summary_text.text(),
        timeout=2000,
    )
    panel = window.findChild(QTextBrowser, "TranslationPanel")
    assert panel is not None
    assert "translation:zh-CN" in panel.toPlainText()


def test_summary_and_translation_languages_are_independent(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    window.summary_lang_combo.setCurrentIndex(window.summary_lang_combo.findData("en"))
    window.translation_lang_combo.setCurrentIndex(window.translation_lang_combo.findData("ja"))

    assert window._resolve_summary_language() == "en"
    assert window._resolve_translation_language() == "ja"

    window.on_translate()
    qtbot.waitUntil(
        lambda: "翻译完成" in window.summary_text.text(),
        timeout=2000,
    )

    assert "translation:ja" in window.translation_panel.toPlainText()


def test_reader_selection_shows_translation_popup(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)
    window.show()

    cursor = window.reader.document().find("First paragraph")
    assert not cursor.isNull()
    window.reader.setTextCursor(cursor)

    body = window.findChild(QLabel, "SelectionTranslationBody")
    assert body is not None
    qtbot.waitUntil(
        lambda: "translation:zh-CN:First paragraph" in body.text(),
        timeout=3000,
    )
    assert window.selection_translation_popup.isVisible()


def test_batch_selection_deletes_checked_feeds_and_exits_mode(qtbot, monkeypatch) -> None:
    window = build_window()
    qtbot.addWidget(window)
    service = window.feed_service

    window.on_batch_delete_feeds()
    window.feed_list.item(2).setCheckState(Qt.Checked)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    window.on_batch_delete_feeds()

    assert service.deleted_feed_batches == [["Engineering"]]
    assert not window.feed_batch_selection_enabled
    assert window.feed_list.count() == 2
    assert window.batch_delete_feed_action.text() == "批量选择"


def test_switching_to_tags_exits_feed_batch_selection(qtbot) -> None:
    window = build_window()
    qtbot.addWidget(window)

    window.on_batch_delete_feeds()
    window.on_tag_tab()

    assert not window.feed_batch_selection_enabled
    assert window.current_sidebar_mode == "tags"
    assert window.batch_delete_feed_action.text() == "批量选择"
    assert not window.cancel_batch_delete_feed_action.isVisible()
