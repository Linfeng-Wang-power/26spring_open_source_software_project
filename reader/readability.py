"""Readable article extraction."""

from __future__ import annotations

from readability import Document

from reader.models import ReadabilityResult


def extract_readable_html(source_html: str) -> ReadabilityResult:
    """Extract main article HTML using readability-lxml."""

    document = Document(source_html)
    title = document.short_title() or document.title()
    content_html = document.summary(html_partial=True)
    return ReadabilityResult(title=title.strip(), content_html=content_html)
