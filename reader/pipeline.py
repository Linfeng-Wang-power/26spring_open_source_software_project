"""High-level reader pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from reader.fetcher import SourceHtmlFetcher
from reader.html_renderer import render_markdown_to_reader_html
from reader.markdown_converter import html_to_markdown
from reader.models import FetchResult, ReaderDocument
from reader.readability import extract_readable_html
from reader.sanitizer import clean_reader_html


@dataclass(frozen=True)
class ReaderPipelineService:
    """Build cleaned HTML, canonical Markdown, and renderable reader HTML."""

    fetcher: SourceHtmlFetcher = SourceHtmlFetcher()

    def fetch_and_process(self, url: str, client: httpx.Client | None = None) -> ReaderDocument:
        fetched = self.fetcher.fetch(url, client=client)
        return self.process_source_html(
            fetched.html,
            source_url=fetched.source_url,
            final_url=fetched.final_url,
        )

    def process_source_html(
        self,
        source_html: str,
        *,
        source_url: str,
        final_url: str | None = None,
    ) -> ReaderDocument:
        resolved_url = final_url or source_url
        readable = extract_readable_html(source_html)
        cleaned_html = clean_reader_html(readable.content_html, resolved_url)
        canonical_markdown = html_to_markdown(cleaned_html)
        reader_html = render_markdown_to_reader_html(
            canonical_markdown,
            title=readable.title,
            source_url=resolved_url,
        )
        return ReaderDocument(
            title=readable.title,
            source_url=source_url,
            final_url=resolved_url,
            source_html=source_html,
            cleaned_html=cleaned_html,
            canonical_markdown=canonical_markdown,
            reader_html=reader_html,
        )

    def render_article_html(self, article: Any) -> str:
        """Compatibility adapter for the current mercury_gui.ReaderPipeline protocol."""

        markdown = getattr(article, "markdown", "") or getattr(article, "summary", "")
        return render_markdown_to_reader_html(
            markdown,
            title=getattr(article, "title", "Untitled"),
            source_url=getattr(article, "url", ""),
        )

    def clean_current_article(self, article: Any) -> str:
        """Return a user-visible summary until persistence is connected."""

        source_html = getattr(article, "source_html", "")
        if source_html:
            document = self.process_source_html(
                source_html,
                source_url=getattr(article, "url", ""),
            )
            return (
                f"已清洗：{document.title}\n\n"
                f"cleaned_html：{len(document.cleaned_html)} 字符\n"
                f"canonical_markdown：{len(document.canonical_markdown)} 字符"
            )

        return (
            f"当前文章暂无 source_html，已使用 Markdown 渲染：{getattr(article, 'title', 'Untitled')}\n\n"
            "后续接入 ContentStore 后会持久化 source_html、cleaned_html 和 canonical_markdown。"
        )
