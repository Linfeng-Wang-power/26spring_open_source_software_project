"""Lumen PySide6 GUI scaffold.

Run:
    python3 mercury_gui.py

Install GUI dependency if needed:
    pip install PySide6
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

import httpx

try:
    from PySide6.QtCore import QObject, Qt, QThread, QSize, Signal, Slot
    from PySide6.QtGui import QAction, QFont, QIcon, QImage, QTextCursor, QTextDocument
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QButtonGroup,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
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

from mercury.storage import StorageService
from mercury.reader import ReaderPipelineService
from mercury.reader.models import ReaderDocument


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
    stable_id: str = ""
    entry_id: str = ""
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

    def list_articles(self, feed_title: str | None = None, unread_only: bool = False) -> list[Article]:
        ...

    def add_feed(self, url: str) -> None:
        ...

    def delete_feed(self, feed_title: str) -> None:
        ...

    def delete_feeds(self, feed_titles: list[str]) -> None:
        ...

    def import_opml(self, path: str) -> None:
        ...

    def refresh_all(self) -> None:
        ...

    def set_article_starred(self, entry_id: str, starred: bool) -> None:
        ...

    def set_article_unread(self, entry_id: str, unread: bool) -> None:
        ...

    def list_tags(self) -> list[tuple[str, int]]:
        ...

    def list_articles_by_tag(self, tag: str, unread_only: bool = False) -> list[Article]:
        ...

    def add_article_tag(self, entry_id: str, tag: str) -> None:
        ...

    def remove_article_tag(self, entry_id: str, tag: str) -> None:
        ...

    def mark_tag_read(self, tag: str) -> None:
        ...

    def star_tag_articles(self, tag: str, starred: bool = True) -> None:
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


class ReaderTextBrowser(QTextBrowser):
    """QTextBrowser with explicit remote image loading for reader content."""

    def __init__(self) -> None:
        super().__init__()
        self._image_cache: dict[str, QImage] = {}

    def loadResource(self, resource_type: int, name: object) -> object:
        image_resource = QTextDocument.ResourceType.ImageResource
        if getattr(resource_type, "value", resource_type) != getattr(image_resource, "value", image_resource):
            return super().loadResource(resource_type, name)

        url = name.toString() if hasattr(name, "toString") else str(name)
        if not url.startswith(("http://", "https://")):
            return super().loadResource(resource_type, name)

        cached = self._image_cache.get(url)
        if cached is not None:
            return cached

        try:
            response = httpx.get(
                url,
                follow_redirects=True,
                timeout=8.0,
                headers={"User-Agent": "MercuryPyQt/0.1 (+local-first RSS reader)"},
            )
            response.raise_for_status()
            image = QImage()
            image.loadFromData(response.content)
        except Exception:
            return super().loadResource(resource_type, name)

        if image.isNull():
            return super().loadResource(resource_type, name)

        self._image_cache[url] = image
        return image


class CleanArticleWorker(QObject):
    """Run article cleaning away from the Qt GUI thread."""

    finished = Signal(object, str, str, str)
    failed = Signal(str)

    def __init__(self, pipeline: ReaderPipeline, article: Article) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.article = article

    @Slot()
    def run(self) -> None:
        try:
            source_html = getattr(self.article, "source_html", "")
            if source_html and hasattr(self.pipeline, "process_source_html"):
                document = self.pipeline.process_source_html(
                    source_html,
                    source_url=self.article.url,
                )
            elif hasattr(self.pipeline, "fetch_and_process"):
                document = self.pipeline.fetch_and_process(self.article.url)
            else:
                self.pipeline.clean_current_article(self.article)
                document = None

            if document is None:
                self.failed.emit("当前 ReaderPipeline 没有返回可保存的清洗结果。")
                return

            message = (
                f"已清洗：{document.title}\n\n"
                f"cleaned_html：{len(document.cleaned_html)} 字符\n"
                f"canonical_markdown：{len(document.canonical_markdown)} 字符"
            )
            self.finished.emit(
                document,
                message,
                getattr(self.article, "entry_id", ""),
                getattr(self.article, "url", ""),
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class RefreshFeedsWorker(QObject):
    """Refresh feeds away from the Qt GUI thread."""

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, feed_service: FeedService) -> None:
        super().__init__()
        self.feed_service = feed_service

    @Slot()
    def run(self) -> None:
        try:
            service = self.feed_service
            if hasattr(service, "create_worker_copy"):
                service = service.create_worker_copy()
            service.refresh_all()
            self.finished.emit(getattr(service, "last_error", "") or "")
        except Exception as exc:
            self.failed.emit(str(exc))


class CleanTagWorker(QObject):
    """Clean all articles under one tag in a background thread."""

    finished = Signal(int, str)
    failed = Signal(str)

    def __init__(self, feed_service: FeedService, pipeline: ReaderPipeline, tag: str) -> None:
        super().__init__()
        self.feed_service = feed_service
        self.pipeline = pipeline
        self.tag = tag

    @Slot()
    def run(self) -> None:
        try:
            service = self.feed_service
            if hasattr(service, "create_worker_copy"):
                service = service.create_worker_copy()
            articles = service.list_articles_by_tag(self.tag)
            cleaned_count = 0
            errors: list[str] = []
            for article in articles:
                try:
                    if not article.entry_id:
                        continue
                    document = self.pipeline.fetch_and_process(article.url)
                    service.save_reader_document(article.entry_id, document)
                    cleaned_count += 1
                except Exception as exc:
                    errors.append(f"{article.title}: {exc}")
            self.finished.emit(cleaned_count, "\n".join(errors))
        except Exception as exc:
            self.failed.emit(str(exc))


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

    def list_articles(self, feed_title: str | None = None, unread_only: bool = False) -> list[Article]:
        if feed_title in (None, "All Feeds"):
            articles = self.articles
        elif feed_title == "Starred":
            articles = [article for article in self.articles if article.starred]
        else:
            articles = [article for article in self.articles if article.feed_title == feed_title]
        if unread_only:
            articles = [article for article in articles if article.unread]
        return articles

    def add_feed(self, url: str) -> None:
        # Interface placeholder: real implementation should validate and persist the feed.
        print(f"TODO FeedService.add_feed({url!r})")

    def delete_feed(self, feed_title: str) -> None:
        self.feeds = [feed for feed in self.feeds if feed.title != feed_title]
        self.articles = [article for article in self.articles if article.feed_title != feed_title]

    def delete_feeds(self, feed_titles: list[str]) -> None:
        for title in feed_titles:
            self.delete_feed(title)

    def import_opml(self, path: str) -> None:
        # Interface placeholder: real implementation should parse OPML and insert feeds.
        print(f"TODO FeedService.import_opml({path!r})")

    def refresh_all(self) -> None:
        # Interface placeholder: real implementation should run feed sync in a worker.
        print("TODO FeedService.refresh_all()")

    def set_article_starred(self, entry_id: str, starred: bool) -> None:
        print(f"TODO FeedService.set_article_starred({entry_id!r}, {starred!r})")

    def set_article_unread(self, entry_id: str, unread: bool) -> None:
        print(f"TODO FeedService.set_article_unread({entry_id!r}, {unread!r})")

    def list_tags(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for article in self.articles:
            for tag in article.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items())

    def list_articles_by_tag(self, tag: str, unread_only: bool = False) -> list[Article]:
        articles = [article for article in self.articles if tag in article.tags]
        if unread_only:
            articles = [article for article in articles if article.unread]
        return articles

    def add_article_tag(self, entry_id: str, tag: str) -> None:
        print(f"TODO FeedService.add_article_tag({entry_id!r}, {tag!r})")

    def remove_article_tag(self, entry_id: str, tag: str) -> None:
        print(f"TODO FeedService.remove_article_tag({entry_id!r}, {tag!r})")

    def mark_tag_read(self, tag: str) -> None:
        print(f"TODO FeedService.mark_tag_read({tag!r})")

    def star_tag_articles(self, tag: str, starred: bool = True) -> None:
        print(f"TODO FeedService.star_tag_articles({tag!r}, {starred!r})")


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


class BatchSummaryDialog(QDialog):
    """Modal progress dialog for batch summary jobs.

    Shows one row per article and updates the leading status icon as the
    worker reports outcomes. Stays open until the user closes it so the
    full report (successes + failures) can be reviewed.
    """

    def __init__(self, titles: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量摘要")
        self.setMinimumSize(520, 380)

        self.progress_label = QLabel("准备开始…")
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        for t in titles:
            QListWidgetItem(f"⏳  {t}", self.list)

        self.cancel_button = QPushButton("取消")
        self.close_button = QPushButton("关闭")
        self.close_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.close_button.clicked.connect(self.accept)

        bbox = QDialogButtonBox()
        bbox.addButton(self.cancel_button, QDialogButtonBox.ActionRole)
        bbox.addButton(self.close_button, QDialogButtonBox.AcceptRole)

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.list, 1)
        layout.addWidget(bbox)

        self._cancel_callback = None

    def set_cancel_callback(self, fn) -> None:
        self._cancel_callback = fn

    def _on_cancel_clicked(self) -> None:
        if self._cancel_callback:
            self._cancel_callback()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText("正在取消…")

    def update_progress(self, current: int, total: int, title: str) -> None:
        self.progress_label.setText(f"({current}/{total}) {title}")
        idx = current - 1
        if 0 <= idx < self.list.count():
            self.list.item(idx).setText(f"⏵  {title}")

    def update_outcome(self, index: int, ok: bool, title: str, detail: str = "") -> None:
        if not (0 <= index < self.list.count()):
            return
        icon = "✓" if ok else "✗"
        text = f"{icon}  {title}"
        if detail:
            text += f"  — {detail}"
        self.list.item(index).setText(text)

    def mark_finished(self, success: int, fail: int, skipped: int) -> None:
        self.progress_label.setText(
            f"完成：成功 {success}，失败 {fail}，跳过 {skipped}"
        )
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)


class SummarySettingsDialog(QDialog):
    """User-facing config for the summary LLM provider.

    base_url + model are stored in SettingsStore. The API key is stored in
    the OS keyring (Keychain on macOS, Credential Locker on Windows). If
    keyring is unavailable, the user is told to use the OPENAI_API_KEY env
    variable.
    """

    def __init__(self, settings_store, current_detail: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("摘要 Provider 设置")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._settings = settings_store

        from mercury.agent.provider.keys import resolve_api_key

        form = QFormLayout()
        self.base_url_edit = QLineEdit(settings_store.get("llm.base_url", ""))
        self.base_url_edit.setPlaceholderText("https://api.openai.com")
        self.model_edit = QLineEdit(settings_store.get("llm.model", ""))
        self.model_edit.setPlaceholderText("gpt-4o-mini")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        existing_key = resolve_api_key()
        if existing_key:
            self.api_key_edit.setPlaceholderText("已存在 (留空则保留)")
        else:
            self.api_key_edit.setPlaceholderText("sk-...")

        self.detail_combo = QComboBox()
        for level, label in (("short", "简短"), ("default", "默认"), ("detailed", "详细")):
            self.detail_combo.addItem(label, level)
        idx = max(0, self.detail_combo.findData(current_detail))
        self.detail_combo.setCurrentIndex(idx)

        form.addRow("Base URL", self.base_url_edit)
        form.addRow("模型", self.model_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("摘要详细度", self.detail_combo)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #888888;")

        self.test_button = QPushButton("测试连接")
        self.test_button.setAutoDefault(False)
        self.test_button.setDefault(False)
        self.test_button.clicked.connect(self._on_test_connection)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.addButton(self.test_button, QDialogButtonBox.ActionRole)
        # Stop Save / Cancel from auto-stealing Enter while the user is in a
        # text field; otherwise typing into Base URL on macOS feels like the
        # focus is "elsewhere" because the default button keeps lighting up.
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)

        # Land the cursor in the first input so the dialog is immediately typable.
        self.base_url_edit.setFocus()

    def _on_test_connection(self) -> None:
        """Send a minimal chat-completions probe so the user knows whether
        base_url / model / key actually work before saving."""
        from mercury.agent.provider.keys import resolve_api_key
        from mercury.agent.provider.llm_provider import (
            ChatMessage,
            ProviderAuthError,
            ProviderConfig,
            ProviderHTTPError,
            ProviderTimeoutError,
        )
        from mercury.agent.provider.openai_compatible import OpenAICompatibleProvider

        base_url = self.base_url_edit.text().strip()
        model = self.model_edit.text().strip()
        # Use the just-typed key when present; otherwise fall back to whatever is
        # already stored so the user can verify an existing key.
        typed_key = self.api_key_edit.text()
        api_key = typed_key or (resolve_api_key() or "")

        missing = []
        if not base_url:
            missing.append("Base URL")
        if not model:
            missing.append("模型")
        if not api_key:
            missing.append("API Key")
        if missing:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText("请先填写: " + ", ".join(missing))
            return

        self.status_label.setStyleSheet("color: #888888;")
        self.status_label.setText("测试中…")
        self.test_button.setEnabled(False)
        QApplication.processEvents()

        config = ProviderConfig(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=15.0,
        )
        try:
            with OpenAICompatibleProvider(config) as provider:
                text = provider.complete([ChatMessage("user", "ping")])
            preview = (text or "").strip().splitlines()[0][:80] if text else "(空响应)"
            self.status_label.setStyleSheet("color: #2e7d32;")
            self.status_label.setText(f"连接成功: {preview}")
        except ProviderAuthError as exc:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"鉴权失败: {exc}")
        except ProviderTimeoutError as exc:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"超时: {exc}")
        except ProviderHTTPError as exc:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"HTTP {exc.status_code}\n{exc}")
        except Exception as exc:
            self.status_label.setStyleSheet("color: #c0392b;")
            self.status_label.setText(f"连接失败: {type(exc).__name__}: {exc}")
        finally:
            self.test_button.setEnabled(True)

    def values(self) -> dict:
        return {
            "base_url": self.base_url_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "api_key": self.api_key_edit.text(),
            "detail_level": self.detail_combo.currentData() or "default",
        }


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

    def __init__(self, article: Article, on_star_clicked: object | None = None) -> None:
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
        title_font = title.font()
        title_font.setBold(article.unread)
        title.setFont(title_font)

        read_state = "未读" if article.unread else "已读"
        meta = QLabel(f"{article.feed_title} · {read_state}\n{article.published}")
        meta.setObjectName("ArticleItemMeta")

        text_box.addWidget(title)
        text_box.addWidget(meta)

        star = QPushButton("★" if article.starred else "☆")
        star.setObjectName("StarButton")
        star.setToolTip("收藏" if not article.starred else "取消收藏")
        star.setFixedWidth(30)
        star.setCursor(Qt.PointingHandCursor)
        if on_star_clicked is not None:
            star.clicked.connect(lambda _checked=False, item=article: on_star_clicked(item))

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
        self.current_sidebar_mode = "feeds"
        self.current_tag: str | None = None
        self.current_articles: list[Article] = []
        self.current_article: Article | None = None
        self.skip_auto_read_entry_id: str | None = None
        self.clean_thread: QThread | None = None
        self.clean_worker: CleanArticleWorker | None = None
        self.refresh_thread: QThread | None = None
        self.refresh_worker: RefreshFeedsWorker | None = None
        self.tag_clean_thread: QThread | None = None
        self.tag_clean_worker: CleanTagWorker | None = None
        self.summary_thread: QThread | None = None
        self.summary_worker = None
        self.summary_active_job = None
        self.summary_job_counter = 0
        self.summary_buffer = ""
        self.summary_detail_level = "default"
        self.summary_target_lang = ""  # "" means follow UI language
        self.batch_summary_thread: QThread | None = None
        self.batch_summary_worker = None
        self._batch_dialog = None
        self._batch_outcome_index = 0
        self.unread_filter_enabled = False
        self.last_refresh_status = "尚未刷新"
        self.sidebar_collapsed = False
        self.sidebar_expanded_width = 225

        self.setWindowTitle("Lumen")
        self.resize(1380, 860)
        self.setMinimumSize(1080, 680)

        store = self._settings_store_or_none()
        if store is not None:
            saved_detail = store.get("summary.detail", "")
            if saved_detail in ("short", "default", "detailed"):
                self.summary_detail_level = saved_detail
            self.summary_target_lang = (store.get("summary.target_lang", "") or "").strip()

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

        app_title = QLabel("  Lumen  ")
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

        self.delete_feed_action = QAction("删除订阅", self)
        self.delete_feed_action.triggered.connect(self.on_delete_feed)
        toolbar.addAction(self.delete_feed_action)

        self.batch_delete_feed_action = QAction("批量删除", self)
        self.batch_delete_feed_action.setToolTip("删除左侧已勾选的订阅")
        self.batch_delete_feed_action.triggered.connect(self.on_batch_delete_feeds)
        toolbar.addAction(self.batch_delete_feed_action)

        self.clean_action = QAction("清洗", self)
        self.clean_action.triggered.connect(self.on_clean_article)
        toolbar.addAction(self.clean_action)

        self.restore_action = QAction("还原", self)
        self.restore_action.setToolTip("显示文章未清洗前的摘要/原始列表内容")
        self.restore_action.triggered.connect(self.on_restore_article)
        toolbar.addAction(self.restore_action)

        self.star_action = QAction("收藏", self)
        self.star_action.triggered.connect(self.on_toggle_starred)
        toolbar.addAction(self.star_action)

        self.read_action = QAction("标记已读", self)
        self.read_action.triggered.connect(self.on_toggle_read_state)
        toolbar.addAction(self.read_action)

        self.add_tag_action = QAction("添加标签", self)
        self.add_tag_action.triggered.connect(self.on_add_article_tag)
        toolbar.addAction(self.add_tag_action)

        self.remove_tag_action = QAction("移除标签", self)
        self.remove_tag_action.triggered.connect(self.on_remove_article_tag)
        toolbar.addAction(self.remove_tag_action)

        self.tag_mark_read_action = QAction("标签标已读", self)
        self.tag_mark_read_action.triggered.connect(self.on_mark_current_tag_read)
        toolbar.addAction(self.tag_mark_read_action)

        self.tag_star_action = QAction("标签收藏", self)
        self.tag_star_action.triggered.connect(self.on_star_current_tag)
        toolbar.addAction(self.tag_star_action)

        self.tag_clean_action = QAction("标签清洗", self)
        self.tag_clean_action.triggered.connect(self.on_clean_current_tag)
        toolbar.addAction(self.tag_clean_action)

        self.summary_action = QAction("摘要", self)
        self.summary_action.triggered.connect(self.on_summary)
        toolbar.addAction(self.summary_action)

        self.batch_summary_action = QAction("批量摘要", self)
        self.batch_summary_action.setToolTip(
            "在文章列表中按住 ⌘ / Ctrl 单击或 Shift 单击多选，然后点这里批量生成摘要"
        )
        self.batch_summary_action.triggered.connect(self.on_batch_summary)
        toolbar.addAction(self.batch_summary_action)

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
        self.sidebar_title = make_section_title("Feeds")
        header.addWidget(self.sidebar_title)
        header.addStretch(1)
        add_feed_btn = QPushButton("+")
        add_feed_btn.setObjectName("IconButton")
        add_feed_btn.setToolTip("添加订阅源")
        add_feed_btn.clicked.connect(self.on_add_feed)
        header.addWidget(add_feed_btn)
        layout.addLayout(header)

        self.feed_list = QListWidget()
        self.feed_list.setObjectName("FeedList")
        self.feed_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.feed_list.currentItemChanged.connect(self.on_sidebar_item_selected)
        self.feed_list.itemSelectionChanged.connect(self._refresh_action_states)
        self.feed_list.itemChanged.connect(lambda _item: self._refresh_action_states())
        layout.addWidget(self.feed_list, 1)

        self.sidebar_footer = QLabel("")
        self.sidebar_footer.setObjectName("SidebarFooter")
        layout.addWidget(self.sidebar_footer)
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

        self.unread_filter_btn = QPushButton("Unread")
        self.unread_filter_btn.setObjectName("SmallToolbarButton")
        self.unread_filter_btn.setToolTip("只显示未读文章")
        self.unread_filter_btn.setCheckable(True)
        self.unread_filter_btn.clicked.connect(self.on_unread_filter)
        header_layout.addWidget(self.unread_filter_btn)
        layout.addWidget(header)

        self.article_list = QListWidget()
        self.article_list.setObjectName("ArticleList")
        self.article_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.article_list.currentItemChanged.connect(self.on_article_selected)
        layout.addWidget(self.article_list, 1)
        return panel

    def _create_reader_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("ReaderPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.reader = ReaderTextBrowser()
        self.reader.setObjectName("Reader")
        self.reader.setOpenExternalLinks(True)
        layout.addWidget(self.reader, 1)
        return panel

    def _create_summary_bar(self) -> QWidget:
        container = QFrame()
        container.setObjectName("SummaryContainer")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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

        layout.addWidget(QLabel("摘要"))
        self.summary_text = QLabel("选择文章后可运行摘要。")
        self.summary_text.setObjectName("SummaryText")
        self.summary_text.setWordWrap(False)
        layout.addWidget(self.summary_text, 1)

        self.summary_lang_combo = QComboBox()
        self.summary_lang_combo.setObjectName("SummaryLangCombo")
        self.summary_lang_combo.setToolTip("摘要语言")
        # Empty value means: follow the UI language (SettingsStore.current_language)
        for value, label in (
            ("", "跟随界面"),
            ("zh-CN", "中文"),
            ("en", "英文"),
            ("ja", "日文"),
        ):
            self.summary_lang_combo.addItem(label, value)
        idx = max(0, self.summary_lang_combo.findData(self.summary_target_lang))
        self.summary_lang_combo.setCurrentIndex(idx)
        self.summary_lang_combo.currentIndexChanged.connect(self._on_summary_lang_changed)
        layout.addWidget(self.summary_lang_combo)

        run_summary_btn = QPushButton("生成摘要")
        run_summary_btn.setObjectName("PrimaryActionButton")
        run_summary_btn.clicked.connect(self.on_summary)
        layout.addWidget(run_summary_btn)

        translate_btn = QPushButton("翻译")
        translate_btn.setObjectName("SecondaryActionButton")
        translate_btn.clicked.connect(self.on_translate)
        layout.addWidget(translate_btn)

        outer.addWidget(bar)

        self.summary_panel = QTextBrowser()
        self.summary_panel.setObjectName("SummaryPanel")
        self.summary_panel.setOpenExternalLinks(True)
        self.summary_panel.setMinimumHeight(180)
        self.summary_panel.setMaximumHeight(280)
        self.summary_panel.setVisible(False)
        outer.addWidget(self.summary_panel)
        self.summary_panel_expanded = False

        return container

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
                border-left: 3px solid transparent;
            }
            QListWidget#ArticleList::item:selected {
                background: #cfe3ff;
                border-left: 3px solid #2469d6;
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
            QPushButton#StarButton {
                border: 0;
                background: transparent;
                color: #0a84ff;
                font-size: 18px;
                padding: 0;
            }
            QPushButton#StarButton:hover {
                background: #edf3ff;
                border-radius: 6px;
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
            QTextBrowser#SummaryPanel {
                background: #fdfdfd;
                border: 0;
                border-top: 1px solid #e5e5e5;
                color: #1f2328;
                padding: 12px 18px;
                font-size: 13px;
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
        selected_title = self.current_feed_title
        self.current_sidebar_mode = "feeds"
        self.current_tag = None
        self.sidebar_title.setText("Feeds")
        previous_block_state = self.feed_list.blockSignals(True)
        self.feed_list.clear()
        try:
            for feed in self.feed_service.list_feeds():
                item = QListWidgetItem()
                label = f"{feed.title} ({feed.unread_count})" if feed.unread_count else feed.title
                item.setText(label)
                item.setData(Qt.UserRole, ("feed", feed.title))
                if feed.title not in {"All Feeds", "Starred"}:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                self.feed_list.addItem(item)
                if feed.title == selected_title:
                    self.feed_list.setCurrentItem(item)
        finally:
            self.feed_list.blockSignals(previous_block_state)
        self._update_sidebar_footer()
        self._refresh_action_states()

    def _load_tags(self) -> None:
        selected_tag = self.current_tag
        self.current_sidebar_mode = "tags"
        self.current_feed_title = None
        self.sidebar_title.setText("Tags")
        previous_block_state = self.feed_list.blockSignals(True)
        self.feed_list.clear()
        try:
            for tag, count in self.feed_service.list_tags():
                item = QListWidgetItem()
                item.setText(f"{tag} ({count})")
                item.setData(Qt.UserRole, ("tag", tag))
                self.feed_list.addItem(item)
                if tag == selected_tag:
                    self.feed_list.setCurrentItem(item)
        finally:
            self.feed_list.blockSignals(previous_block_state)
        self._update_sidebar_footer()
        self._refresh_action_states()

    def _load_articles(self, feed_title: str | None = None) -> None:
        if self.current_sidebar_mode == "tags" and self.current_tag:
            self.current_articles = self.feed_service.list_articles_by_tag(
                self.current_tag,
                unread_only=self.unread_filter_enabled,
            )
            scope = f"Tag: {self.current_tag}"
        else:
            self.current_articles = self.feed_service.list_articles(
                feed_title,
                unread_only=self.unread_filter_enabled,
            )
            scope = feed_title or "All Feeds"
        self.article_list.clear()
        self.article_scope_label.setText(f"{scope} · 未读" if self.unread_filter_enabled else scope)
        self.unread_filter_btn.setChecked(self.unread_filter_enabled)

        for article in self.current_articles:
            item = QListWidgetItem()
            widget = ArticleListItem(article, self.on_toggle_starred_from_list)
            item.setSizeHint(QSize(280, 72))
            item.setData(Qt.UserRole, article)
            self.article_list.addItem(item)
            self.article_list.setItemWidget(item, widget)

        if self.current_articles:
            self.article_list.setCurrentRow(0)
        else:
            self.current_article = None
            self.reader.setHtml("<p style='padding:32px;color:#777;'>没有文章。</p>")
            self._refresh_action_states()

    def _update_sidebar_footer(self) -> None:
        if self.current_sidebar_mode == "tags":
            tag_count = len(self.feed_service.list_tags())
            self.sidebar_footer.setText(f"Tags: {tag_count}\nLast refresh: {self.last_refresh_status}")
            return

        feeds = self.feed_service.list_feeds()
        real_feeds = [feed for feed in feeds if feed.title not in {"All Feeds", "Starred"}]
        unread = next((feed.unread_count for feed in feeds if feed.title == "All Feeds"), 0)
        self.sidebar_footer.setText(
            f"Feeds: {len(real_feeds)} · Unread: {unread}\nLast refresh: {self.last_refresh_status}"
        )

    def _show_article(self, article: Article) -> None:
        should_skip_auto_read = (
            article.unread
            and article.entry_id
            and self.skip_auto_read_entry_id == article.entry_id
        )
        if should_skip_auto_read:
            self.skip_auto_read_entry_id = None
        elif article.unread and getattr(article, "entry_id", ""):
            try:
                self.feed_service.set_article_unread(article.entry_id, False)
                article = replace(article, unread=False)
                current_item = self.article_list.currentItem()
                if current_item is not None:
                    # Update the item's stored Article in place. Replacing the
                    # item widget here would clobber any multi-selection the
                    # user has built up via Shift / Ctrl click.
                    current_item.setData(Qt.UserRole, article)
                self._load_feeds()
            except Exception as exc:
                self._show_error_dialog("更新已读状态失败", str(exc))

        self.current_article = article
        cached_document = self._cached_reader_document(article)
        if cached_document is not None:
            self.reader.setHtml(cached_document.reader_html)
        else:
            self.reader.setHtml(self.reader_pipeline.render_article_html(article))
        self._restore_summary_for_article(article)
        self._refresh_action_states()

    def _cached_reader_document(self, article: Article) -> ReaderDocument | None:
        entry_id = getattr(article, "entry_id", "")
        if not entry_id or not hasattr(self.feed_service, "get_reader_document"):
            return None
        return self.feed_service.get_reader_document(entry_id)

    def _refresh_action_states(self) -> None:
        article = self.current_article
        has_article = article is not None
        can_delete_feed = (
            self.current_sidebar_mode == "feeds"
            and bool(self._selected_feed_titles() or self.current_feed_title not in (None, "All Feeds", "Starred"))
        )
        has_tag = self.current_sidebar_mode == "tags" and bool(self.current_tag)

        self.refresh_action.setEnabled(not (self.refresh_thread and self.refresh_thread.isRunning()))
        self.delete_feed_action.setEnabled(can_delete_feed)
        self.batch_delete_feed_action.setEnabled(self.current_sidebar_mode == "feeds" and bool(self._checked_feed_titles()))
        self.clean_action.setEnabled(has_article and not (self.clean_thread and self.clean_thread.isRunning()))
        self.restore_action.setEnabled(has_article)
        self.star_action.setEnabled(has_article)
        self.read_action.setEnabled(has_article)
        self.add_tag_action.setEnabled(has_article)
        self.remove_tag_action.setEnabled(has_article and bool(article.tags if article else ()))
        self.tag_mark_read_action.setEnabled(has_tag)
        self.tag_star_action.setEnabled(has_tag)
        self.tag_clean_action.setEnabled(has_tag and not (self.tag_clean_thread and self.tag_clean_thread.isRunning()))

        if has_article:
            self.star_action.setText("取消收藏" if article.starred else "收藏")
            self.read_action.setText("标记未读" if not article.unread else "标记已读")
        else:
            self.star_action.setText("收藏")
            self.read_action.setText("标记已读")

    def _reload_articles_preserving_selection(self, entry_id: str | None = None) -> None:
        target_entry_id = entry_id or getattr(self.current_article, "entry_id", "")
        if self.current_sidebar_mode == "tags":
            self._load_tags()
            self.current_articles = self.feed_service.list_articles_by_tag(
                self.current_tag or "",
                unread_only=self.unread_filter_enabled,
            )
            scope = f"Tag: {self.current_tag}" if self.current_tag else "Tags"
        else:
            self._load_feeds()
            self.current_articles = self.feed_service.list_articles(
                self.current_feed_title,
                unread_only=self.unread_filter_enabled,
            )
            scope = self.current_feed_title or "All Feeds"
        self.article_list.clear()
        self.article_scope_label.setText(
            f"{scope} · 未读" if self.unread_filter_enabled else scope
        )

        selected_row = 0
        for index, article in enumerate(self.current_articles):
            item = QListWidgetItem()
            widget = ArticleListItem(article, self.on_toggle_starred_from_list)
            item.setSizeHint(QSize(280, 72))
            item.setData(Qt.UserRole, article)
            self.article_list.addItem(item)
            self.article_list.setItemWidget(item, widget)
            if target_entry_id and article.entry_id == target_entry_id:
                selected_row = index

        if self.current_articles:
            self.article_list.setCurrentRow(selected_row)
        else:
            self.current_article = None
            self.reader.setHtml("<p style='padding:32px;color:#777;'>没有文章。</p>")
            self._refresh_action_states()

    # -----------------------------
    # Event handlers
    # -----------------------------

    def on_sidebar_item_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        item_type, value = current.data(Qt.UserRole)
        if item_type == "tag":
            self.current_sidebar_mode = "tags"
            self.current_tag = value
            self.current_feed_title = None
            self._load_articles(None)
            return

        self.current_sidebar_mode = "feeds"
        self.current_tag = None
        self.current_feed_title = value
        self._load_articles(value)

    def on_article_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        article = current.data(Qt.UserRole)
        if article is not None and hasattr(article, "title"):
            self._show_article(article)

    def on_search_changed(self, text: str) -> None:
        lowered = text.strip().lower()
        if lowered.startswith("tag:"):
            tag = text.strip()[4:].strip()
            if tag:
                self.current_articles = self.feed_service.list_articles_by_tag(
                    tag,
                    unread_only=self.unread_filter_enabled,
                )
                self.article_list.clear()
                self.article_scope_label.setText(f"Search tag: {tag}")
                for article in self.current_articles:
                    item = QListWidgetItem()
                    widget = ArticleListItem(article, self.on_toggle_starred_from_list)
                    item.setSizeHint(QSize(280, 72))
                    item.setData(Qt.UserRole, article)
                    self.article_list.addItem(item)
                    self.article_list.setItemWidget(item, widget)
                if self.current_articles:
                    self.article_list.setCurrentRow(0)
                else:
                    self.current_article = None
                    self.reader.setHtml("<p style='padding:32px;color:#777;'>没有匹配标签的文章。</p>")
                    self._refresh_action_states()
                return

        if not lowered and self.article_scope_label.text().startswith("Search tag:"):
            self._load_articles(self.current_feed_title)
            return

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
            self.summary_text.setText("侧边栏已展开。")
        else:
            self.sidebar_expanded_width = max(180, sizes[0])
            self.main_splitter.setSizes([0, sizes[1], sizes[2] + sizes[0]])
            self.sidebar_collapsed = True
            self.summary_text.setText("侧边栏已收起。")

    def on_feed_tab(self) -> None:
        self.current_feed_title = self.current_feed_title or "All Feeds"
        self._load_feeds()
        self._load_articles(self.current_feed_title)

    def on_tag_tab(self) -> None:
        self._load_tags()
        if self.feed_list.count() > 0:
            self.feed_list.setCurrentRow(0)
        else:
            self.current_tag = None
            self.current_articles = []
            self.article_list.clear()
            self.article_scope_label.setText("Tags")
            self.reader.setHtml("<p style='padding:32px;color:#777;'>还没有标签。</p>")
            self.summary_text.setText("可以给文章添加自定义标签。")
            self._refresh_action_states()

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
        self.unread_filter_enabled = self.unread_filter_btn.isChecked()
        self._load_articles(self.current_feed_title)
        state = "开启" if self.unread_filter_enabled else "关闭"
        self.summary_text.setText(f"未读筛选已{state}。")

    def on_summary_panel_toggle(self) -> None:
        self.summary_panel_expanded = not self.summary_panel_expanded
        self.summary_panel.setVisible(self.summary_panel_expanded)
        self.summary_toggle.setText("⌄" if self.summary_panel_expanded else "⌃")

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

    def on_delete_feed(self) -> None:
        if self.current_sidebar_mode != "feeds":
            return
        selected_titles = self._selected_feed_titles()
        if not selected_titles and self.current_feed_title not in (None, "All Feeds", "Starred"):
            selected_titles = [self.current_feed_title]
        if not selected_titles:
            return

        title_text = "、".join(selected_titles[:3])
        if len(selected_titles) > 3:
            title_text += f" 等 {len(selected_titles)} 个订阅"
        result = QMessageBox.question(
            self,
            "删除订阅",
            f"确定要删除订阅“{title_text}”吗？\n相关文章和清洗缓存也会从本地数据库删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        try:
            if len(selected_titles) == 1:
                self.feed_service.delete_feed(selected_titles[0])
            else:
                self.feed_service.delete_feeds(selected_titles)
        except Exception as exc:
            self._show_error_dialog("删除订阅失败", str(exc))
            return

        self.current_feed_title = "All Feeds"
        self.current_article = None
        self._load_feeds()
        self._load_articles(self.current_feed_title)
        self.summary_text.setText(f"已删除 {len(selected_titles)} 个订阅。")

    def on_batch_delete_feeds(self) -> None:
        if self.current_sidebar_mode != "feeds":
            return
        checked_titles = self._checked_feed_titles()
        if not checked_titles:
            self.summary_text.setText("请先勾选要删除的订阅。")
            return

        title_text = "、".join(checked_titles[:3])
        if len(checked_titles) > 3:
            title_text += f" 等 {len(checked_titles)} 个订阅"
        result = QMessageBox.question(
            self,
            "批量删除订阅",
            f"确定要删除“{title_text}”吗？\n相关文章和清洗缓存也会从本地数据库删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        try:
            self.feed_service.delete_feeds(checked_titles)
        except Exception as exc:
            self._show_error_dialog("批量删除订阅失败", str(exc))
            return

        self.current_feed_title = "All Feeds"
        self.current_article = None
        self._load_feeds()
        self._load_articles(self.current_feed_title)
        self.summary_text.setText(f"已批量删除 {len(checked_titles)} 个订阅。")

    def _selected_feed_titles(self) -> list[str]:
        titles: list[str] = []
        for item in self.feed_list.selectedItems():
            data = item.data(Qt.UserRole)
            if not data:
                continue
            item_type, value = data
            if item_type == "feed" and value not in {"All Feeds", "Starred"}:
                titles.append(value)
        return titles

    def _checked_feed_titles(self) -> list[str]:
        titles: list[str] = []
        for row in range(self.feed_list.count()):
            item = self.feed_list.item(row)
            data = item.data(Qt.UserRole)
            if not data:
                continue
            item_type, value = data
            if (
                item_type == "feed"
                and value not in {"All Feeds", "Starred"}
                and item.checkState() == Qt.Checked
            ):
                titles.append(value)
        return titles

    def on_toggle_starred(self) -> None:
        if not self.current_article:
            return
        self.on_toggle_starred_from_list(self.current_article)

    def on_toggle_starred_from_list(self, article: Article) -> None:
        try:
            self.feed_service.set_article_starred(article.entry_id, not article.starred)
        except Exception as exc:
            self._show_error_dialog("收藏状态更新失败", str(exc))
            return
        self._reload_articles_preserving_selection(article.entry_id)

    def on_toggle_read_state(self) -> None:
        if not self.current_article:
            return
        article = self.current_article
        new_unread = not article.unread
        try:
            self.feed_service.set_article_unread(article.entry_id, new_unread)
        except Exception as exc:
            self._show_error_dialog("已读状态更新失败", str(exc))
            return
        if new_unread:
            self.skip_auto_read_entry_id = article.entry_id
        self._reload_articles_preserving_selection(article.entry_id)

    def on_add_article_tag(self) -> None:
        if not self.current_article:
            return
        tag, accepted = QInputDialog.getText(
            self,
            "添加标签",
            "请输入标签名称：",
            text="稍后读",
        )
        if not accepted or not tag.strip():
            return
        try:
            self.feed_service.add_article_tag(self.current_article.entry_id, tag.strip())
        except Exception as exc:
            self._show_error_dialog("添加标签失败", str(exc))
            return
        self.summary_text.setText(f"已添加标签：{tag.strip()}")
        if self.current_sidebar_mode == "tags":
            self._load_tags()
        self._reload_articles_preserving_selection(self.current_article.entry_id)

    def on_remove_article_tag(self) -> None:
        if not self.current_article or not self.current_article.tags:
            return
        tag, accepted = QInputDialog.getItem(
            self,
            "移除标签",
            "请选择要移除的标签：",
            list(self.current_article.tags),
            0,
            False,
        )
        if not accepted or not tag:
            return
        try:
            self.feed_service.remove_article_tag(self.current_article.entry_id, tag)
        except Exception as exc:
            self._show_error_dialog("移除标签失败", str(exc))
            return
        self.summary_text.setText(f"已移除标签：{tag}")
        if self.current_sidebar_mode == "tags":
            self._load_tags()
        self._reload_articles_preserving_selection(self.current_article.entry_id)

    def on_mark_current_tag_read(self) -> None:
        if not self.current_tag:
            return
        try:
            self.feed_service.mark_tag_read(self.current_tag)
        except Exception as exc:
            self._show_error_dialog("标签批量标已读失败", str(exc))
            return
        self.summary_text.setText(f"标签“{self.current_tag}”下的文章已标记为已读。")
        self._reload_articles_preserving_selection()

    def on_star_current_tag(self) -> None:
        if not self.current_tag:
            return
        try:
            self.feed_service.star_tag_articles(self.current_tag, True)
        except Exception as exc:
            self._show_error_dialog("标签批量收藏失败", str(exc))
            return
        self.summary_text.setText(f"标签“{self.current_tag}”下的文章已收藏。")
        self._reload_articles_preserving_selection()

    def on_clean_current_tag(self) -> None:
        if not self.current_tag:
            return
        if self.tag_clean_thread is not None and self.tag_clean_thread.isRunning():
            self.summary_text.setText("标签批量清洗正在进行，请稍候。")
            return

        tag = self.current_tag
        self.tag_clean_action.setEnabled(False)
        self.summary_text.setText(f"正在后台清洗标签“{tag}”下的文章。")
        self.tag_clean_thread = QThread(self)
        self.tag_clean_worker = CleanTagWorker(self.feed_service, self.reader_pipeline, tag)
        self.tag_clean_worker.moveToThread(self.tag_clean_thread)
        self.tag_clean_thread.started.connect(self.tag_clean_worker.run)
        self.tag_clean_worker.finished.connect(self.on_clean_current_tag_finished)
        self.tag_clean_worker.failed.connect(self.on_clean_current_tag_failed)
        self.tag_clean_worker.finished.connect(self.tag_clean_thread.quit)
        self.tag_clean_worker.failed.connect(self.tag_clean_thread.quit)
        self.tag_clean_thread.finished.connect(self.tag_clean_worker.deleteLater)
        self.tag_clean_thread.finished.connect(self.tag_clean_thread.deleteLater)
        self.tag_clean_thread.finished.connect(self._clear_tag_clean_worker)
        self.tag_clean_thread.start()

    @Slot(int, str)
    def on_clean_current_tag_finished(self, cleaned_count: int, errors: str) -> None:
        self.summary_text.setText(f"标签批量清洗完成：{cleaned_count} 篇。")
        self._reload_articles_preserving_selection()
        if errors:
            self._show_error_dialog("部分文章清洗失败", errors)

    @Slot(str)
    def on_clean_current_tag_failed(self, message: str) -> None:
        self.summary_text.setText("标签批量清洗失败。")
        self._show_error_dialog("标签批量清洗失败", message)

    @Slot()
    def _clear_tag_clean_worker(self) -> None:
        self.tag_clean_thread = None
        self.tag_clean_worker = None
        self._refresh_action_states()

    def on_restore_article(self) -> None:
        if not self.current_article:
            return
        self.reader.setHtml(self.reader_pipeline.render_article_html(self.current_article))
        self.summary_text.setText(f"已还原未清洗显示：{self.current_article.title}")

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
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            self.summary_text.setText("订阅刷新正在进行，请稍候。")
            return

        self.refresh_action.setEnabled(False)
        self.summary_text.setText("正在后台刷新订阅源。")
        self.refresh_thread = QThread(self)
        self.refresh_worker = RefreshFeedsWorker(self.feed_service)
        self.refresh_worker.moveToThread(self.refresh_thread)
        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self.on_refresh_all_finished)
        self.refresh_worker.failed.connect(self.on_refresh_all_failed)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_worker.failed.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self.refresh_worker.deleteLater)
        self.refresh_thread.finished.connect(self.refresh_thread.deleteLater)
        self.refresh_thread.finished.connect(self._clear_refresh_worker)
        self.refresh_thread.start()

    @Slot(str)
    def on_refresh_all_finished(self, last_error: str) -> None:
        self.last_refresh_status = datetime.now().strftime("%H:%M:%S")
        if self.current_sidebar_mode == "tags":
            self._load_tags()
        else:
            self._load_feeds()
        self._load_articles(self.current_feed_title)
        if last_error:
            self.summary_text.setText(f"刷新完成于 {self.last_refresh_status}，但部分订阅失败。")
            self._show_error_dialog("部分订阅刷新失败", last_error)
        else:
            self.summary_text.setText(f"订阅刷新完成：{self.last_refresh_status}")

    @Slot(str)
    def on_refresh_all_failed(self, message: str) -> None:
        self.summary_text.setText("订阅刷新失败。")
        self._show_error_dialog("刷新订阅失败", message)

    @Slot()
    def _clear_refresh_worker(self) -> None:
        self.refresh_thread = None
        self.refresh_worker = None
        self.refresh_action.setEnabled(True)

    def on_clean_article(self) -> None:
        if not self.current_article:
            return
        if self.clean_thread is not None and self.clean_thread.isRunning():
            self.summary_text.setText("内容清洗正在进行，请稍候。")
            return

        self.clean_action.setEnabled(False)
        self.summary_text.setText(f"正在清洗：{self.current_article.title}")

        self.clean_thread = QThread(self)
        self.clean_worker = CleanArticleWorker(self.reader_pipeline, self.current_article)
        self.clean_worker.moveToThread(self.clean_thread)
        self.clean_thread.started.connect(self.clean_worker.run)
        self.clean_worker.finished.connect(self.on_clean_article_finished)
        self.clean_worker.failed.connect(self.on_clean_article_failed)
        self.clean_worker.finished.connect(self.clean_thread.quit)
        self.clean_worker.failed.connect(self.clean_thread.quit)
        self.clean_thread.finished.connect(self.clean_worker.deleteLater)
        self.clean_thread.finished.connect(self.clean_thread.deleteLater)
        self.clean_thread.finished.connect(self._clear_clean_worker)
        self.clean_thread.start()

    @Slot(object, str, str, str)
    def on_clean_article_finished(
        self,
        document: ReaderDocument,
        message: str,
        entry_id: str,
        article_url: str,
    ) -> None:
        if entry_id and hasattr(self.feed_service, "save_reader_document"):
            try:
                self.feed_service.save_reader_document(entry_id, document)
            except Exception as exc:
                self._show_error_dialog("保存清洗结果失败", str(exc))

        current_entry_id = getattr(self.current_article, "entry_id", "") if self.current_article else ""
        current_url = getattr(self.current_article, "url", "") if self.current_article else ""
        if (entry_id and entry_id == current_entry_id) or (not entry_id and article_url == current_url):
            self.reader.setHtml(document.reader_html)
            self.summary_text.setText(f"已清洗并显示：{document.title}")
        else:
            self.summary_text.setText(f"已清洗并缓存：{document.title}")

    @Slot(str)
    def on_clean_article_failed(self, message: str) -> None:
        self.summary_text.setText("内容清洗失败。")
        self._show_error_dialog("内容清洗失败", message)

    @Slot()
    def _clear_clean_worker(self) -> None:
        self.clean_thread = None
        self.clean_worker = None
        self._refresh_action_states()

    def on_summary(self) -> None:
        if not self.current_article:
            return
        # If a job is already running for any entry, the second click cancels it.
        if self.summary_thread is not None and self.summary_worker is not None:
            self.summary_worker.request_cancel()
            self.summary_text.setText("正在取消摘要…")
            return

        agent = self._ensure_summary_agent()
        if agent is None:
            return

        article = self.current_article
        entry_id = getattr(article, "entry_id", "") or ""
        content = self._summary_input_for(article)
        if not content.strip():
            self._show_error_dialog("无法生成摘要", "当前文章没有可用的正文。")
            return

        target_lang = self._resolve_target_language()

        from mercury.agent.summary.summary_agent import SummaryRequest
        from mercury.agent.summary.summary_worker import SummaryJob, SummaryWorker

        self.summary_job_counter += 1
        job = SummaryJob(job_id=self.summary_job_counter, entry_id=entry_id)
        self.summary_active_job = job
        self.summary_buffer = ""

        request = SummaryRequest(
            entry_id=entry_id,
            title=article.title or "",
            content=content,
            target_language=target_lang,
            detail_level=self.summary_detail_level,
        )

        thread = QThread(self)
        worker = SummaryWorker(agent, request, job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.started.connect(self._on_summary_started)
        worker.token.connect(self._on_summary_token)
        worker.finished.connect(self._on_summary_finished)
        worker.failed.connect(self._on_summary_failed)
        worker.cancelled.connect(self._on_summary_cancelled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(self._clear_summary_worker)

        self.summary_thread = thread
        self.summary_worker = worker
        thread.start()

        self.summary_text.setText("正在生成摘要…")

    # -- Summary helpers -----------------------------------------------------

    def _ensure_summary_agent(self):
        """Return an agent, or None after showing a config dialog."""
        agent = getattr(self, "summary_agent", None)
        if agent is not None and not isinstance(agent, MockSummaryAgent):
            return agent

        try:
            from mercury.agent.summary.runtime_config import build_runtime
        except Exception as exc:
            self._show_error_dialog("摘要功能未就绪", str(exc))
            return None

        runtime, status = build_runtime(self._settings_store_or_none())
        if runtime is None:
            self._show_error_dialog(
                "摘要 Provider 未配置",
                f"{status.reason}\n\n请在设置中填写 Base URL / 模型 / API Key 后再试。",
            )
            return None

        self.summary_agent = runtime
        return runtime

    def _settings_store_or_none(self):
        return getattr(self.feed_service, "settings_store", None)

    def _resolve_target_language(self) -> str:
        """Pick the summary language: explicit override, else UI language, else zh-CN."""
        if self.summary_target_lang:
            return self.summary_target_lang
        store = self._settings_store_or_none()
        if store is not None and hasattr(store, "current_language"):
            return store.current_language() or "zh-CN"
        return "zh-CN"

    @Slot(int)
    def _on_summary_lang_changed(self, _index: int) -> None:
        value = self.summary_lang_combo.currentData() or ""
        self.summary_target_lang = value
        store = self._settings_store_or_none()
        if store is not None:
            store.set("summary.target_lang", value)

    def _summary_input_for(self, article: Article) -> str:
        """Prefer canonical_markdown from the reader pipeline, else article.summary."""
        entry_id = getattr(article, "entry_id", "") or ""
        document = self._cached_reader_document(article)
        if document is not None and document.canonical_markdown.strip():
            return document.canonical_markdown
        return article.summary or ""

    def _summary_store(self):
        return getattr(self.feed_service, "summary_store", None)

    def _restore_summary_for_article(self, article: Article) -> None:
        store = self._summary_store()
        entry_id = getattr(article, "entry_id", "") or ""
        if store is None or not entry_id:
            self.summary_text.setText("选择文章后可运行摘要。")
            self._render_summary_panel("")
            return
        try:
            cached = store.get(entry_id)
        except Exception:
            cached = None
        if cached:
            self.summary_text.setText(self._summary_status_preview(cached))
            self._render_summary_panel(cached)
            self._auto_expand_summary_panel()
        else:
            self.summary_text.setText(f"已打开：{article.title}")
            self._render_summary_panel("")

    def _render_summary_panel(self, text: str) -> None:
        if not text:
            self.summary_panel.clear()
            return
        try:
            self.summary_panel.setMarkdown(text)
        except Exception:
            self.summary_panel.setPlainText(text)
        # Keep view scrolled to the latest content during streaming.
        cursor = self.summary_panel.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.summary_panel.setTextCursor(cursor)

    def _auto_expand_summary_panel(self) -> None:
        if not self.summary_panel_expanded:
            self.summary_panel_expanded = True
            self.summary_panel.setVisible(True)
            self.summary_toggle.setText("⌄")

    @staticmethod
    def _summary_status_preview(text: str) -> str:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        return first_line[:60] + ("…" if len(first_line) > 60 else "")

    @Slot(int, str)
    def _on_summary_started(self, job_id: int, entry_id: str) -> None:
        if not self._is_active_summary_job(job_id, entry_id):
            return
        self.summary_text.setText("正在生成摘要…")
        self._render_summary_panel("")
        self._auto_expand_summary_panel()

    @Slot(int, str, str)
    def _on_summary_token(self, job_id: int, entry_id: str, chunk: str) -> None:
        if not self._is_active_summary_job(job_id, entry_id):
            return
        self.summary_buffer += chunk
        if self._is_current_entry(entry_id):
            self.summary_text.setText(f"生成中… {len(self.summary_buffer)} 字")
            self._render_summary_panel(self.summary_buffer)

    @Slot(int, str, str, str, bool)
    def _on_summary_finished(
        self,
        job_id: int,
        entry_id: str,
        full_text: str,
        model_id: str,
        truncated: bool,
    ) -> None:
        if not self._is_active_summary_job(job_id, entry_id):
            return
        store = self._summary_store()
        if store is not None and full_text.strip():
            try:
                store.save_result(entry_id, full_text, model_id)
            except Exception as exc:
                self._show_error_dialog("摘要保存失败", str(exc))
        if self._is_current_entry(entry_id):
            preview = self._summary_status_preview(full_text)
            if truncated:
                preview = "[已裁剪] " + preview
            self.summary_text.setText(preview)
            self._render_summary_panel(full_text)
            self._auto_expand_summary_panel()

    @Slot(int, str, str)
    def _on_summary_failed(self, job_id: int, entry_id: str, message: str) -> None:
        if not self._is_active_summary_job(job_id, entry_id):
            return
        if self._is_current_entry(entry_id):
            self.summary_text.setText("摘要生成失败。")
        self._show_error_dialog("摘要生成失败", message)

    @Slot(int, str)
    def _on_summary_cancelled(self, job_id: int, entry_id: str) -> None:
        if not self._is_active_summary_job(job_id, entry_id):
            return
        if self._is_current_entry(entry_id):
            self._restore_summary_for_article(self.current_article)

    @Slot()
    def _clear_summary_worker(self) -> None:
        self.summary_thread = None
        self.summary_worker = None
        self.summary_active_job = None
        self.summary_buffer = ""

    def _is_active_summary_job(self, job_id: int, entry_id: str) -> bool:
        active = self.summary_active_job
        return (
            active is not None
            and active.job_id == job_id
            and active.entry_id == entry_id
        )

    def _is_current_entry(self, entry_id: str) -> bool:
        current = getattr(self.current_article, "entry_id", "") if self.current_article else ""
        return bool(entry_id) and entry_id == current

    # -- Batch summary -------------------------------------------------------

    def on_batch_summary(self) -> None:
        articles = self._selected_articles_for_batch()
        if not articles:
            self._show_error_dialog(
                "未选择文章",
                "请在文章列表中按住 Ctrl 或 Shift 选择多篇文章后再使用批量摘要。",
            )
            return
        if self.batch_summary_thread is not None:
            self._show_error_dialog(
                "批量摘要进行中",
                "请等待当前批量任务完成或取消后再启动新的批量任务。",
            )
            return

        agent = self._ensure_summary_agent()
        if agent is None:
            return

        store = self._summary_store()
        target_lang = self._resolve_target_language()
        items: list = []
        from mercury.agent.summary.batch_worker import BatchSummaryItem
        from mercury.agent.summary.summary_agent import SummaryRequest

        for article in articles:
            entry_id = getattr(article, "entry_id", "") or ""
            content = self._summary_input_for(article)
            request = SummaryRequest(
                entry_id=entry_id,
                title=article.title or "",
                content=content,
                target_language=target_lang,
                detail_level=self.summary_detail_level,
            )
            items.append(
                BatchSummaryItem(
                    entry_id=entry_id,
                    title=article.title or entry_id,
                    request=request,
                )
            )

        from mercury.agent.summary.batch_worker import BatchSummaryWorker

        dialog = BatchSummaryDialog([it.title for it in items], self)
        thread = QThread(self)
        worker = BatchSummaryWorker(agent, items)
        worker.moveToThread(thread)
        dialog.set_cancel_callback(worker.request_cancel)

        # Stash the dialog and a per-item index counter on self so the slot
        # method (which runs on the GUI thread) can access them.
        self._batch_dialog = dialog
        self._batch_outcome_index = 0

        worker.progress.connect(dialog.update_progress, Qt.QueuedConnection)
        worker.item_done.connect(self._on_batch_item_done, Qt.QueuedConnection)
        worker.finished.connect(dialog.mark_finished, Qt.QueuedConnection)
        worker.cancelled.connect(dialog.mark_finished, Qt.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(self._clear_batch_summary_worker)

        thread.started.connect(worker.run)
        self.batch_summary_thread = thread
        self.batch_summary_worker = worker
        thread.start()

        dialog.exec()
        # When the dialog is closed mid-run, also cancel.
        if self.batch_summary_worker is not None:
            self.batch_summary_worker.request_cancel()

    def _selected_articles_for_batch(self) -> list[Article]:
        items = self.article_list.selectedItems()
        articles: list[Article] = []
        seen = set()
        for it in items:
            data = it.data(Qt.UserRole)
            # Duck-typing: feed_service may return a feed-layer Article that is
            # a different class from mercury_gui.Article. Accept anything that
            # quacks like an article row.
            if data is None or not hasattr(data, "title") or not hasattr(data, "entry_id"):
                continue
            key = data.entry_id or id(data)
            if key in seen:
                continue
            seen.add(key)
            articles.append(data)
        # Fallback so single-click + 批量摘要 still does something useful.
        if not articles and self.current_article is not None:
            articles.append(self.current_article)
        return articles

    @Slot(object)
    def _on_batch_item_done(self, outcome) -> None:
        """Handle a single batch outcome on the GUI thread.

        Persisting summaries here (instead of in the worker thread) means we
        reuse the main SQLite connection without violating sqlite3's
        single-thread guarantee. Errors are surfaced to the dialog row instead
        of being silently swallowed so the user can see when persistence fails.
        """
        dialog = getattr(self, "_batch_dialog", None)
        idx = self._batch_outcome_index
        self._batch_outcome_index += 1

        detail = ""
        if outcome.skipped:
            detail = outcome.error or "已跳过"
        elif not outcome.ok:
            detail = (outcome.error or "失败")[:120]

        if outcome.ok and outcome.entry_id and outcome.text:
            store = self._summary_store()
            if store is not None:
                try:
                    store.save_result(
                        outcome.entry_id, outcome.text, outcome.model_id
                    )
                except Exception as exc:
                    detail = f"保存失败: {exc}"
            # If the saved entry is the one currently open, refresh the panel.
            if self._is_current_entry(outcome.entry_id):
                self._restore_summary_for_article(self.current_article)

        if dialog is not None:
            dialog.update_outcome(idx, outcome.ok, outcome.title, detail)

    @Slot()
    def _clear_batch_summary_worker(self) -> None:
        self.batch_summary_thread = None
        self.batch_summary_worker = None
        self._batch_dialog = None
        self._batch_outcome_index = 0

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
        store = self._settings_store_or_none()
        if store is None:
            self._show_error_dialog(
                "设置不可用",
                "当前 FeedService 没有暴露 settings_store。",
            )
            return

        dialog = SummarySettingsDialog(store, self.summary_detail_level, self)
        if dialog.exec() != QDialog.Accepted:
            return

        values = dialog.values()
        store.set("llm.base_url", values["base_url"])
        store.set("llm.model", values["model"])
        store.set("summary.detail", values["detail_level"])
        self.summary_detail_level = values["detail_level"]

        api_key = values["api_key"]
        if api_key:
            from mercury.agent.provider.keys import store_api_key

            saved = store_api_key(api_key)
            if not saved:
                self._show_error_dialog(
                    "API Key 未保存",
                    "无法访问系统 keyring。请改用 OPENAI_API_KEY 环境变量。",
                )

        # Force re-bootstrap so next "生成摘要" picks up new config.
        self.summary_agent = MockSummaryAgent()
        self.summary_text.setText("Provider 设置已保存。")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Lumen")
    app.setOrganizationName("Lumen Study Group")

    window = MercuryMainWindow(
        feed_service=StorageService(),
        reader_pipeline=ReaderPipelineService(),
        summary_agent=MockSummaryAgent(),
        translation_agent=MockTranslationAgent(),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
