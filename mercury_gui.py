"""Mercury PySide6 GUI scaffold.

Run:
    python3 mercury_gui.py

Install GUI dependency if needed:
    pip install PySide6
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol

try:
    from PySide6.QtCore import Qt, QSize
    from PySide6.QtGui import QAction, QFont, QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QFrame,
        QFileDialog,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QSplitter,
        QTextBrowser,
        QToolBar,
        QVBoxLayout,
        QWidget,
        QLineEdit,
    )
except ModuleNotFoundError as exc:
    print("PySide6 未安装。请先运行：pip install PySide6")
    raise SystemExit(1) from exc

from mercury_feed import LocalFeedService
from reader import ReaderPipelineService


# -----------------------------
# Domain models
# -----------------------------


@dataclass(frozen=True)
class Feed:
    """Feed metadata shown in the sidebar."""

    title: str
    url: str
    unread_count: int = 0


@dataclass(frozen=True)
class Article:
    """Reader-facing article DTO.

    Later this should come from EntryStore + ContentStore instead of sample data.
    """

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


# -----------------------------
# Service interfaces
# -----------------------------


class FeedService(Protocol):
    """Feed / OPML boundary.

    Real implementation should use feedparser + httpx + xml.etree.ElementTree.
    """

    def list_feeds(self) -> list[Feed]:
        ...

    def list_articles(self, feed_title: str | None = None) -> list[Article]:
        ...

    def add_feed(self, url: str) -> None:
        ...

    def import_opml(self, path: str) -> None:
        ...

    def refresh_all(self) -> None:
        ...


class ReaderPipeline(Protocol):
    """Reader pipeline boundary.

    Target pipeline:
    source_html -> cleaned_html -> canonical_markdown -> reader_html.
    """

    def render_article_html(self, article: Article) -> str:
        ...

    def clean_current_article(self, article: Article) -> str:
        ...


class LLMProvider(Protocol):
    """Model-neutral provider boundary.

    Real implementation should support OpenAI-compatible APIs and local models.
    """

    def test_connection(self) -> bool:
        ...


class SummaryAgent(Protocol):
    """Summary Agent boundary."""

    def summarize(self, article: Article) -> str:
        ...


class TranslationAgent(Protocol):
    """Translation Agent boundary."""

    def translate(self, article: Article, target_language: str = "zh-CN") -> str:
        ...


class SettingsStore(Protocol):
    """Settings boundary for UI preferences and provider metadata."""

    def current_language(self) -> str:
        ...


# -----------------------------
# Mock services for GUI scaffold
# -----------------------------


SAMPLE_FEEDS = [
    Feed("All Feeds", "internal://all", 0),
    Feed("Starred", "internal://starred", 92),
    Feed("simonwillison.net", "https://simonwillison.net/atom/everything/", 6),
    Feed("geohot.github.io", "https://geohot.github.io/blog/feed.xml", 3),
    Feed("anildash.com", "https://www.anildash.com/feed.xml", 8),
    Feed("blog.jim-nielsen.com", "https://blog.jim-nielsen.com/feed.xml", 4),
    Feed("buttondown.com/hillelwayne", "https://buttondown.email/hillelwayne/rss", 7),
    Feed("daringfireball.net", "https://daringfireball.net/feeds/main", 5),
    Feed("devblogs.microsoft.com", "https://devblogs.microsoft.com/feed/", 10),
]


SAMPLE_ARTICLES = [
    Article(
        title="Vibe coding SwiftUI apps is a lot of fun",
        feed_title="simonwillison.net",
        author="Simon Willison",
        published="2026 年 3 月 27 日",
        url="https://simonwillison.net/2026/Mar/27/vibe-coding/",
        summary="这篇文章讨论了使用 AI 辅助构建桌面应用的体验，并强调快速原型和人工判断的重要性。",
        markdown=(
            "我有一台新的笔记本，早期体验显示它非常适合运行本地大模型。"
            "我对现有性能监控工具不太满意，于是尝试用 AI 辅助写一个替代工具。\n\n"
            "这已经是我第二次实验用 AI 构建桌面应用。结果说明，当需求边界清晰、"
            "反馈及时且架构简单时，AI 可以非常快地帮助完成可用原型。\n\n"
            "对于 Mercury 来说，这个经验对应到我们的开发方法：先写 INIT、AGENTS、PLAN，"
            "再用小步里程碑实现 Feed、Reader、Summary 和 Translation。"
        ),
        tags=("AI Coding", "Desktop", "Local-first"),
        starred=True,
    ),
    Article(
        title="Python Vulnerability Lookup",
        feed_title="simonwillison.net",
        author="Simon Willison",
        published="2026 年 3 月 30 日",
        url="https://example.com/python-vulnerability-lookup",
        summary="一个关于 Python 安全漏洞查询工具的短文。",
        markdown="这篇示例文章用于展示 Mercury 的文章列表、星标状态和 Reader 面板。",
        tags=("Python", "Security"),
        starred=True,
    ),
    Article(
        title="Two Worlds",
        feed_title="geohot.github.io",
        author="George Hotz",
        published="2026 年 3 月 30 日",
        url="https://example.com/two-worlds",
        summary="一篇关于工程取舍与工具链选择的示例文章。",
        markdown="Mercury 的技术选型需要同时满足本地优先、跨平台和模型中立。",
        tags=("Engineering",),
        starred=True,
    ),
    Article(
        title="Endgame for the Open Web",
        feed_title="anildash.com",
        author="Anil Dash",
        published="2026 年 3 月 27 日",
        url="https://example.com/open-web",
        summary="关于开放 Web 和信息阅读体验的文章。",
        markdown="Feed 阅读器的价值在于把分散的信息源聚合到用户可以控制的本地工具中。",
        tags=("Web", "RSS"),
    ),
    Article(
        title="Package Managers Need to Cool Down",
        feed_title="buttondown.com/hillelwayne",
        author="Hillel Wayne",
        published="2026 年 3 月 25 日",
        url="https://example.com/package-managers",
        summary="关于软件包管理器复杂性的讨论。",
        markdown="技术选型时应该考虑生态、复杂度、可维护性和打包成本。",
        tags=("Tools", "Packaging"),
        starred=True,
    ),
]


class MockFeedService:
    """Sample implementation. Replace with real FeedService later."""

    def __init__(self) -> None:
        self.feeds = SAMPLE_FEEDS
        self.articles = SAMPLE_ARTICLES

    def list_feeds(self) -> list[Feed]:
        return self.feeds

    def list_articles(self, feed_title: str | None = None) -> list[Article]:
        if feed_title in (None, "All Feeds"):
            return self.articles
        if feed_title == "Starred":
            return [article for article in self.articles if article.starred]
        return [article for article in self.articles if article.feed_title == feed_title]

    def add_feed(self, url: str) -> None:
        # Interface placeholder: real implementation should validate and persist the feed.
        print(f"TODO FeedService.add_feed({url!r})")

    def import_opml(self, path: str) -> None:
        # Interface placeholder: real implementation should parse OPML and insert feeds.
        print(f"TODO FeedService.import_opml({path!r})")

    def refresh_all(self) -> None:
        # Interface placeholder: real implementation should run feed sync in a worker.
        print("TODO FeedService.refresh_all()")


class MockReaderPipeline:
    """Sample reader pipeline. Replace with readability/Markdown renderer later."""

    def render_article_html(self, article: Article) -> str:
        paragraphs = "".join(f"<p>{part}</p>" for part in article.markdown.split("\n\n"))
        tags = "".join(f"<span class='tag'>{tag}</span>" for tag in article.tags)
        return f"""
        <html>
          <head>
            <style>
              body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
                color: #202124;
                background: #ffffff;
                margin: 0;
                padding: 34px 54px 80px 54px;
                line-height: 1.72;
                font-size: 18px;
              }}
              h1 {{
                font-size: 34px;
                line-height: 1.18;
                margin: 0 0 18px 0;
                letter-spacing: 0;
              }}
              .meta {{
                color: #555;
                font-size: 15px;
                margin-bottom: 28px;
              }}
              .author {{
                font-style: italic;
                color: #222;
              }}
              p {{
                margin: 0 0 20px 0;
              }}
              .tags {{
                margin-top: 28px;
              }}
              .tag {{
                display: inline-block;
                padding: 5px 10px;
                margin-right: 8px;
                border-radius: 12px;
                background: #edf3ff;
                color: #2458a6;
                font-size: 13px;
              }}
            </style>
          </head>
          <body>
            <h1>{article.title}</h1>
            <div class="meta">
              <span class="author">{article.author}</span><br/>
              {article.published}<br/>
              {article.url}
            </div>
            {paragraphs}
            <div class="tags">{tags}</div>
          </body>
        </html>
        """

    def clean_current_article(self, article: Article) -> str:
        # Interface placeholder: real pipeline should persist cleaned_html + markdown.
        return f"已清洗：{article.title}\n\n输出：cleaned_html + canonical_markdown"


class MockSummaryAgent:
    """Sample Summary Agent. Replace with LLM-backed executor later."""

    def summarize(self, article: Article) -> str:
        return article.summary


class MockTranslationAgent:
    """Sample Translation Agent. Replace with segment-based Translation Agent later."""

    def translate(self, article: Article, target_language: str = "zh-CN") -> str:
        return (
            f"翻译占位：目标语言 {target_language}\n\n"
            f"文章《{article.title}》之后会通过 TranslationAgent 按段落翻译，"
            "并在 Reader 中显示原文 / 译文对照。"
        )


# -----------------------------
# GUI helpers
# -----------------------------


def make_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def make_small_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SmallLabel")
    return label


class PillButton(QPushButton):
    """Small segmented-control style button."""

    def __init__(self, text: str, checked: bool = False) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(28)


class ArticleListItem(QWidget):
    """Custom article row matching the compact Mercury list style."""

    def __init__(self, article: Article) -> None:
        super().__init__()
        self.article = article

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 10, 8)
        root.setSpacing(8)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        title = QLabel(article.title)
        title.setObjectName("ArticleItemTitle")
        title.setWordWrap(True)

        meta = QLabel(f"{article.feed_title}\n{article.published}")
        meta.setObjectName("ArticleItemMeta")

        text_box.addWidget(title)
        text_box.addWidget(meta)

        star = QLabel("★" if article.starred else "☆")
        star.setObjectName("StarLabel")
        star.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        root.addLayout(text_box, 1)
        root.addWidget(star)


class MercuryMainWindow(QMainWindow):
    """Main Mercury window.

    This class intentionally wires only UI + service interfaces.
    Real network/database/LLM work should be implemented behind services.
    """

    def __init__(
        self,
        feed_service: FeedService,
        reader_pipeline: ReaderPipeline,
        summary_agent: SummaryAgent,
        translation_agent: TranslationAgent,
    ) -> None:
        super().__init__()
        self.feed_service = feed_service
        self.reader_pipeline = reader_pipeline
        self.summary_agent = summary_agent
        self.translation_agent = translation_agent

        self.current_feed_title: str | None = "Starred"
        self.current_articles: list[Article] = []
        self.current_article: Article | None = None
        self.sidebar_collapsed = False
        self.sidebar_expanded_width = 225

        self.setWindowTitle("Mercury")
        self.resize(1380, 860)
        self.setMinimumSize(1080, 680)

        self._build_toolbar()
        self._build_layout()
        self._apply_styles()
        self._load_feeds()
        self._load_articles(self.current_feed_title)

    # -----------------------------
    # UI construction
    # -----------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setObjectName("TopToolbar")
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        app_title = QLabel("  Mercury  ")
        app_title.setObjectName("ToolbarTitle")
        toolbar.addWidget(app_title)
        toolbar.addSeparator()

        self.sidebar_action = QAction("侧边栏", self)
        self.sidebar_action.setToolTip("收起 / 展开左侧订阅栏")
        self.sidebar_action.triggered.connect(self.on_toggle_sidebar)
        toolbar.addAction(self.sidebar_action)

        # These actions are interface placeholders for future module wiring.
        self.refresh_action = QAction("刷新", self)
        self.refresh_action.triggered.connect(self.on_refresh_all)
        toolbar.addAction(self.refresh_action)

        self.import_opml_action = QAction("导入 OPML", self)
        self.import_opml_action.triggered.connect(self.on_import_opml)
        toolbar.addAction(self.import_opml_action)

        self.clean_action = QAction("清洗", self)
        self.clean_action.triggered.connect(self.on_clean_article)
        toolbar.addAction(self.clean_action)

        self.summary_action = QAction("摘要", self)
        self.summary_action.triggered.connect(self.on_summary)
        toolbar.addAction(self.summary_action)

        self.translation_action = QAction("翻译", self)
        self.translation_action.triggered.connect(self.on_translate)
        toolbar.addAction(self.translation_action)

        self.settings_action = QAction("设置", self)
        self.settings_action.triggered.connect(self.on_open_settings)
        toolbar.addAction(self.settings_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("搜索文章")
        self.search_box.setFixedWidth(260)
        self.search_box.textChanged.connect(self.on_search_changed)
        toolbar.addWidget(self.search_box)

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        self.main_splitter.setChildrenCollapsible(False)

        self.sidebar = self._create_sidebar()
        self.article_panel = self._create_article_panel()
        self.reader_panel = self._create_reader_panel()

        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.article_panel)
        self.main_splitter.addWidget(self.reader_panel)
        self.main_splitter.setSizes([self.sidebar_expanded_width, 315, 840])

        root_layout.addWidget(self.main_splitter, 1)
        root_layout.addWidget(self._create_summary_bar())
        self.setCentralWidget(root)

    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(10)

        segment = QHBoxLayout()
        segment.setSpacing(0)
        self.feed_tab = PillButton("Feeds", checked=True)
        self.tag_tab = PillButton("Tags")
        self.feed_tab.clicked.connect(self.on_feed_tab)
        self.tag_tab.clicked.connect(self.on_tag_tab)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.feed_tab)
        group.addButton(self.tag_tab)
        segment.addWidget(self.feed_tab)
        segment.addWidget(self.tag_tab)
        segment.addStretch(1)
        layout.addLayout(segment)

        header = QHBoxLayout()
        header.addWidget(make_section_title("Feeds"))
        header.addStretch(1)
        add_feed_btn = QPushButton("+")
        add_feed_btn.setObjectName("IconButton")
        add_feed_btn.setToolTip("添加订阅源")
        add_feed_btn.clicked.connect(self.on_add_feed)
        header.addWidget(add_feed_btn)
        layout.addLayout(header)

        self.feed_list = QListWidget()
        self.feed_list.setObjectName("FeedList")
        self.feed_list.currentItemChanged.connect(self.on_feed_selected)
        layout.addWidget(self.feed_list, 1)

        footer = QLabel("Feeds: 86 · Entries: 3054 · Unread: 0\nLast sync: 2m ago")
        footer.setObjectName("SidebarFooter")
        layout.addWidget(footer)
        return sidebar

    def _create_article_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ArticlePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("ArticleHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        self.article_scope_label = QLabel("Starred")
        self.article_scope_label.setObjectName("ArticleScope")
        header_layout.addWidget(self.article_scope_label)
        header_layout.addStretch(1)

        more_btn = QPushButton("⋯")
        more_btn.setObjectName("SmallToolbarButton")
        more_btn.setToolTip("更多筛选")
        more_btn.clicked.connect(self.on_more_filters)
        header_layout.addWidget(more_btn)

        unread_btn = QPushButton("Unread")
        unread_btn.setObjectName("SmallToolbarButton")
        unread_btn.setToolTip("未读过滤接口占位")
        unread_btn.clicked.connect(self.on_unread_filter)
        header_layout.addWidget(unread_btn)
        layout.addWidget(header)

        self.article_list = QListWidget()
        self.article_list.setObjectName("ArticleList")
        self.article_list.currentItemChanged.connect(self.on_article_selected)
        layout.addWidget(self.article_list, 1)
        return panel

    def _create_reader_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ReaderPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.reader = QTextBrowser()
        self.reader.setObjectName("Reader")
        self.reader.setOpenExternalLinks(True)
        layout.addWidget(self.reader, 1)
        return panel

    def _create_summary_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("SummaryBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self.summary_toggle = QPushButton("⌃")
        self.summary_toggle.setObjectName("SummaryToggle")
        self.summary_toggle.setFixedWidth(32)
        self.summary_toggle.setToolTip("展开 / 收起摘要面板")
        self.summary_toggle.clicked.connect(self.on_summary_panel_toggle)
        layout.addWidget(self.summary_toggle)

        layout.addWidget(QLabel("Summary"))
        self.summary_text = QLabel("选择文章后可运行摘要。")
        self.summary_text.setObjectName("SummaryText")
        self.summary_text.setWordWrap(False)
        layout.addWidget(self.summary_text, 1)

        run_summary_btn = QPushButton("生成摘要")
        run_summary_btn.setObjectName("PrimaryActionButton")
        run_summary_btn.clicked.connect(self.on_summary)
        layout.addWidget(run_summary_btn)

        translate_btn = QPushButton("翻译")
        translate_btn.setObjectName("SecondaryActionButton")
        translate_btn.clicked.connect(self.on_translate)
        layout.addWidget(translate_btn)
        return bar

    # -----------------------------
    # Styling
    # -----------------------------

    def _apply_styles(self) -> None:
        self.setFont(QFont("Microsoft YaHei", 10))
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f7f7f7;
                color: #1f2328;
            }
            QToolBar#TopToolbar {
                background: #fbfbfb;
                border: 0;
                border-bottom: 1px solid #e5e5e5;
                spacing: 8px;
                min-height: 42px;
                padding: 4px 8px;
            }
            QLabel#ToolbarTitle {
                color: #4a4a4a;
                font-size: 16px;
                font-weight: 700;
            }
            QLineEdit#SearchBox {
                min-height: 28px;
                border: 1px solid #e2e2e2;
                border-radius: 14px;
                padding: 0 12px;
                background: #ffffff;
                color: #333333;
            }
            QFrame#Sidebar {
                background: #f5f5f5;
                border-right: 1px solid #dddddd;
            }
            QFrame#ArticlePanel {
                background: #ffffff;
                border-right: 1px solid #dddddd;
            }
            QFrame#ReaderPanel {
                background: #ffffff;
            }
            QLabel#SectionTitle {
                font-size: 14px;
                font-weight: 700;
                color: #2b2b2b;
            }
            QLabel#SmallLabel {
                font-size: 12px;
                color: #777777;
            }
            QPushButton {
                border: 0;
                border-radius: 7px;
                padding: 6px 10px;
                background: transparent;
                color: #202124;
            }
            QPushButton:hover {
                background: #ececec;
            }
            QPushButton:checked {
                background: #0a84ff;
                color: white;
                font-weight: 700;
            }
            QPushButton#IconButton {
                min-width: 26px;
                max-width: 26px;
                min-height: 24px;
                padding: 0;
                font-size: 18px;
            }
            QPushButton#SmallToolbarButton {
                background: #eeeeee;
                border-radius: 7px;
                min-height: 26px;
                padding: 4px 10px;
            }
            QPushButton#PrimaryActionButton {
                background: #0a84ff;
                color: white;
                font-weight: 700;
                border-radius: 8px;
            }
            QPushButton#SecondaryActionButton {
                background: #eeeeee;
                color: #1f2328;
                border-radius: 8px;
            }
            QListWidget {
                border: 0;
                outline: 0;
                background: transparent;
            }
            QListWidget#FeedList::item {
                min-height: 30px;
                padding: 4px 8px;
                border-radius: 7px;
                color: #111111;
            }
            QListWidget#FeedList::item:selected {
                background: #dcdcdc;
                color: #111111;
            }
            QListWidget#ArticleList::item {
                border-bottom: 1px solid #eeeeee;
            }
            QListWidget#ArticleList::item:selected {
                background: #dddddd;
            }
            QFrame#ArticleHeader {
                background: #ffffff;
                border-bottom: 1px solid #e8e8e8;
                min-height: 42px;
            }
            QLabel#ArticleScope {
                font-size: 14px;
                font-weight: 700;
                color: #222222;
            }
            QLabel#ArticleItemTitle {
                font-size: 13px;
                font-weight: 600;
                color: #333333;
            }
            QLabel#ArticleItemMeta {
                font-size: 11px;
                line-height: 1.3;
                color: #858585;
            }
            QLabel#StarLabel {
                color: #0a84ff;
                font-size: 18px;
            }
            QLabel#SidebarFooter {
                font-size: 11px;
                color: #8a8a8a;
                padding: 6px 2px;
            }
            QTextBrowser#Reader {
                border: 0;
                background: #ffffff;
            }
            QFrame#SummaryBar {
                background: #fbfbfb;
                border-top: 1px solid #dddddd;
                min-height: 42px;
            }
            QPushButton#SummaryToggle {
                background: transparent;
                color: #444444;
                padding: 0;
            }
            QLabel#SummaryText {
                color: #666666;
            }
            QSplitter::handle {
                background: #dddddd;
            }
            QSplitter::handle:horizontal {
                width: 1px;
            }
            """
        )

    def _show_interface_dialog(
        self,
        *,
        title: str,
        module: str,
        interface: str,
        current: str,
        next_step: str,
        risk: str,
    ) -> None:
        """Show a polished placeholder dialog for unfinished module interfaces."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Information)
        dialog.setTextFormat(Qt.RichText)
        dialog.setText(
            f"""
            <div style="font-family:'Microsoft YaHei', sans-serif; min-width:460px;">
              <h2 style="margin:0 0 10px 0; color:#1f2328;">{title}</h2>
              <p style="margin:0 0 14px 0; color:#667085;">
                当前是 GUI 原型阶段。这个控件已经保留接口，后续可以直接接入真实模块。
              </p>
              <table cellspacing="0" cellpadding="6" style="font-size:13px;">
                <tr>
                  <td style="color:#667085; white-space:nowrap;">对应模块</td>
                  <td><b>{module}</b></td>
                </tr>
                <tr>
                  <td style="color:#667085; white-space:nowrap;">接口名称</td>
                  <td><code>{interface}</code></td>
                </tr>
                <tr>
                  <td style="color:#667085; white-space:nowrap;">当前行为</td>
                  <td>{current}</td>
                </tr>
                <tr>
                  <td style="color:#667085; white-space:nowrap;">下一步</td>
                  <td>{next_step}</td>
                </tr>
                <tr>
                  <td style="color:#667085; white-space:nowrap;">主要风险</td>
                  <td>{risk}</td>
                </tr>
              </table>
            </div>
            """
        )
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.button(QMessageBox.Ok).setText("知道了")
        dialog.setStyleSheet(
            """
            QMessageBox {
                background: #ffffff;
            }
            QMessageBox QLabel {
                color: #1f2328;
            }
            QPushButton {
                min-width: 86px;
                min-height: 30px;
                border: 0;
                border-radius: 8px;
                background: #0a84ff;
                color: white;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #0072df;
            }
            """
        )
        dialog.exec()

    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show a compact error dialog for Feed/OPML runtime failures."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setTextFormat(Qt.RichText)
        dialog.setText(
            f"""
            <div style="font-family:'Microsoft YaHei', sans-serif; min-width:420px;">
              <h2 style="margin:0 0 10px 0; color:#b42318;">{title}</h2>
              <p style="margin:0; color:#344054;">{message}</p>
            </div>
            """
        )
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.button(QMessageBox.Ok).setText("知道了")
        dialog.setStyleSheet(
            """
            QMessageBox {
                background: #ffffff;
            }
            QPushButton {
                min-width: 86px;
                min-height: 30px;
                border: 0;
                border-radius: 8px;
                background: #b42318;
                color: white;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #912018;
            }
            """
        )
        dialog.exec()

    # -----------------------------
    # Data loading and UI projection
    # -----------------------------

    def _load_feeds(self) -> None:
        self.feed_list.clear()
        for feed in self.feed_service.list_feeds():
            item = QListWidgetItem()
            label = f"{feed.title} ({feed.unread_count})" if feed.unread_count else feed.title
            item.setText(label)
            item.setData(Qt.UserRole, feed.title)
            self.feed_list.addItem(item)
            if feed.title == self.current_feed_title:
                self.feed_list.setCurrentItem(item)

    def _load_articles(self, feed_title: str | None = None) -> None:
        self.current_articles = self.feed_service.list_articles(feed_title)
        self.article_list.clear()
        self.article_scope_label.setText(feed_title or "All Feeds")

        for article in self.current_articles:
            item = QListWidgetItem()
            widget = ArticleListItem(article)
            item.setSizeHint(QSize(280, 72))
            item.setData(Qt.UserRole, article)
            self.article_list.addItem(item)
            self.article_list.setItemWidget(item, widget)

        if self.current_articles:
            self.article_list.setCurrentRow(0)
        else:
            self.current_article = None
            self.reader.setHtml("<p style='padding:32px;color:#777;'>没有文章。</p>")

    def _show_article(self, article: Article) -> None:
        self.current_article = article
        self.reader.setHtml(self.reader_pipeline.render_article_html(article))
        self.summary_text.setText(f"已打开：{article.title}")

    # -----------------------------
    # Event handlers
    # -----------------------------

    def on_feed_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        feed_title = current.data(Qt.UserRole)
        self.current_feed_title = feed_title
        self._load_articles(feed_title)

    def on_article_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        article = current.data(Qt.UserRole)
        if article is not None and hasattr(article, "title"):
            self._show_article(article)

    def on_search_changed(self, text: str) -> None:
        # Interface placeholder: real search should query EntryStore by title/summary.
        lowered = text.strip().lower()
        for row in range(self.article_list.count()):
            item = self.article_list.item(row)
            article = item.data(Qt.UserRole)
            visible = not lowered or lowered in article.title.lower() or lowered in article.summary.lower()
            item.setHidden(not visible)

    def on_toggle_sidebar(self) -> None:
        """Collapse or restore the feed sidebar.

        We keep the same widget alive so the selected feed and scroll state survive.
        """
        sizes = self.main_splitter.sizes()
        if not sizes:
            return

        if self.sidebar_collapsed:
            restored_reader_width = max(520, sizes[2] - self.sidebar_expanded_width)
            self.main_splitter.setSizes([self.sidebar_expanded_width, sizes[1], restored_reader_width])
            self.sidebar_collapsed = False
            self._show_interface_dialog(
                title="侧边栏已展开",
                module="GUI / 体验",
                interface="MainWindow.on_toggle_sidebar()",
                current="恢复左侧 Feed / Tags 导航栏，保留当前选择和列表状态。",
                next_step="后续可把折叠状态保存到 QSettings，重启应用后自动恢复。",
                risk="跨平台 DPI 和窗口尺寸不同，折叠宽度需要用 QSplitter 动态计算。",
            )
        else:
            self.sidebar_expanded_width = max(180, sizes[0])
            self.main_splitter.setSizes([0, sizes[1], sizes[2] + sizes[0]])
            self.sidebar_collapsed = True
            self._show_interface_dialog(
                title="侧边栏已收起",
                module="GUI / 体验",
                interface="MainWindow.on_toggle_sidebar()",
                current="将左侧 Feed / Tags 导航栏宽度设为 0，让 Reader 区获得更多空间。",
                next_step="后续可增加窄栏图标模式，而不是完全隐藏侧边栏。",
                risk="收起后用户需要明确知道如何恢复，因此工具栏入口必须保持可见。",
            )

    def on_feed_tab(self) -> None:
        self._show_interface_dialog(
            title="Feeds 视图",
            module="GUI / Feed",
            interface="FeedService.list_feeds()",
            current="当前显示 mock Feed 列表，包括 All Feeds、Starred 和示例订阅源。",
            next_step="接入真实 FeedStore，从 SQLite 读取订阅源和未读数量。",
            risk="Feed 数量多时需要虚拟列表或分组，否则侧边栏可能变慢。",
        )

    def on_tag_tab(self) -> None:
        self._show_interface_dialog(
            title="Tags 视图",
            module="后续功能 / Tags",
            interface="TagService.list_tags()",
            current="当前只是保留入口，MVP 阶段不实现完整标签库。",
            next_step="MVP 稳定后再接入标签筛选、标签库维护和 AI tag suggestions。",
            risk="标签系统容易扩大范围，当前应避免影响 Feed、Reader、Summary、Translation 主线。",
        )

    def on_more_filters(self) -> None:
        self._show_interface_dialog(
            title="更多筛选",
            module="GUI / EntryList",
            interface="EntryQueryBuilder",
            current="当前只保留按钮入口，还没有真实筛选菜单。",
            next_step="接入按 Feed、未读、星标、搜索关键字组合查询的 EntryStore 接口。",
            risk="筛选条件必须和数据库查询一致，不能只在 UI 层隐藏条目。",
        )

    def on_unread_filter(self) -> None:
        self._show_interface_dialog(
            title="未读过滤",
            module="Feed + 本地存储",
            interface="EntryStore.list_entries(unread_only=True)",
            current="当前按钮只是占位，不会改变 mock 数据。",
            next_step="接入 SQLite 的 read_state 字段，点击后刷新文章列表。",
            risk="批量标记已读和筛选条件要保持一致，避免用户看到过期列表。",
        )

    def on_summary_panel_toggle(self) -> None:
        self._show_interface_dialog(
            title="Summary 面板",
            module="GUI / Summary Agent",
            interface="SummaryPanel.toggle()",
            current="当前底部只显示一行摘要状态，尚未实现展开面板。",
            next_step="实现可展开的摘要面板，包含目标语言、详细程度、生成、取消、复制、清除。",
            risk="摘要生成是长任务，必须通过 AgentRuntime 投射状态，不能阻塞 GUI。",
        )

    def on_add_feed(self) -> None:
        url, accepted = QInputDialog.getText(
            self,
            "添加订阅源",
            "请输入 RSS / Atom Feed URL：",
            text="https://",
        )
        if not accepted or not url.strip():
            return
        try:
            self.feed_service.add_feed(url.strip())
            self._load_feeds()
            self._load_articles(self.current_feed_title)
        except Exception as exc:
            self._show_error_dialog("添加订阅源失败", str(exc))
            return
        self._show_interface_dialog(
            title="添加订阅源",
            module="Feed / OPML",
            interface="FeedService.add_feed(url)",
            current=f"已调用真实 FeedService.add_feed()：{url.strip()}",
            next_step="后续由本地存储组把 JSON cache 替换为 SQLite FeedStore / EntryStore。",
            risk="Feed URL 可能重定向、不可访问或不是有效 RSS / Atom，需要清晰错误提示。",
        )

    def on_import_opml(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "导入 OPML",
            "",
            "OPML Files (*.opml *.xml);;All Files (*)",
        )
        if not path:
            return
        try:
            self.feed_service.import_opml(path)
            self._load_feeds()
            self._load_articles(self.current_feed_title)
        except Exception as exc:
            self._show_error_dialog("导入 OPML 失败", str(exc))
            return
        self._show_interface_dialog(
            title="导入 OPML",
            module="Feed / OPML",
            interface="FeedService.import_opml(path)",
            current=f"已从文件导入订阅源：{path}",
            next_step="点击刷新后会逐个拉取导入的订阅源，并将 entries 写入缓存；后续接入 SQLite。",
            risk="OPML 可能包含重复订阅、无效 URL 或嵌套分组，导入逻辑必须幂等。",
        )

    def on_refresh_all(self) -> None:
        # Interface placeholder: real sync must run in a worker, not in the GUI thread.
        try:
            self.feed_service.refresh_all()
            self._load_feeds()
            self._load_articles(self.current_feed_title)
        except Exception as exc:
            self._show_error_dialog("刷新订阅失败", str(exc))
            return
        self.summary_text.setText("刷新接口已触发：之后接入 SyncService + TaskQueue。")
        last_error = getattr(self.feed_service, "last_error", None)
        self._show_interface_dialog(
            title="刷新订阅",
            module="Feed + 本地存储",
            interface="SyncService.refresh_all()",
            current="已调用真实 refresh_all()。"
            + (f"<br/><br/>部分订阅失败：<br/><code>{last_error}</code>" if last_error else ""),
            next_step="当前使用 httpx + 标准库 XML 解析 RSS / Atom；后续可替换为 feedparser 并写入 SQLite。",
            risk="网络请求不能在 GUI 线程运行；单个 Feed 失败不能中断全部同步。",
        )

    def on_clean_article(self) -> None:
        if not self.current_article:
            return
        message = self.reader_pipeline.clean_current_article(self.current_article)
        self._show_interface_dialog(
            title="内容清洗",
            module="内容清洗 / ReaderPipeline",
            interface="ReaderPipeline.clean_current_article(article)",
            current=message,
            next_step="接入 httpx、readability-lxml、BeautifulSoup4、bleach、markdownify，生成 cleaned HTML 和 canonical Markdown。",
            risk="图片、表格、代码块、相对链接容易在 HTML -> Markdown 过程中丢失或退化。",
        )

    def on_summary(self) -> None:
        if not self.current_article:
            return
        # Interface placeholder: real SummaryAgent should run through AgentRuntime.
        summary = self.summary_agent.summarize(self.current_article)
        self.summary_text.setText(summary)
        self._show_interface_dialog(
            title="生成摘要",
            module="Summary Agent",
            interface="SummaryAgent.summarize(article)",
            current=f"当前从 mock article 返回示例摘要：{summary}",
            next_step="接入 YAML prompt template、LLMProvider、AgentRuntime，并把成功摘要保存到 SQLite。",
            risk="长文可能超出 token；模型可能产生幻觉；失败或取消不能覆盖已有成功摘要。",
        )

    def on_translate(self) -> None:
        if not self.current_article:
            return
        # Interface placeholder: real TranslationAgent should segment and persist results.
        translation = self.translation_agent.translate(self.current_article)
        self.summary_text.setText("TranslationAgent 接口已调用。")
        self._show_interface_dialog(
            title="翻译文章",
            module="Translation / Provider",
            interface="TranslationAgent.translate(article, target_language)",
            current=translation,
            next_step="接入 segment extractor、YAML prompt template、LLMProvider，并在 Reader 中显示原文 / 译文对照。",
            risk="Provider 兼容性、超时、段落数量不匹配、长文翻译成本都需要单独处理。",
        )

    def on_open_settings(self) -> None:
        # Interface placeholder: connect to provider/model/agent settings dialog.
        self._show_interface_dialog(
            title="设置",
            module="Provider / Settings",
            interface="SettingsDialog + ProviderStore",
            current="当前只保留设置入口，尚未实现真实设置页面。",
            next_step="实现 Provider、Model、Summary、Translation、语言和本地存储设置页。",
            risk="API Key 不应明文写入数据库或日志；Provider base URL path 需要测试避免 404。",
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Mercury")
    app.setOrganizationName("Mercury Study Group")

    window = MercuryMainWindow(
        feed_service=LocalFeedService(),
        reader_pipeline=ReaderPipelineService(),
        summary_agent=MockSummaryAgent(),
        translation_agent=MockTranslationAgent(),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
