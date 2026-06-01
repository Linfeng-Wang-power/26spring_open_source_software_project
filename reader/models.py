"""DTOs used by the reader pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchResult:
    """Fetched source HTML and resolved URL."""

    source_url: str
    final_url: str
    html: str


@dataclass(frozen=True)
class ReadabilityResult:
    """Main article content extracted from source HTML."""

    title: str
    content_html: str


@dataclass(frozen=True)
class ReaderDocument:
    """All rebuildable reader representations for an article."""

    title: str
    source_url: str
    final_url: str
    source_html: str
    cleaned_html: str
    canonical_markdown: str
    reader_html: str
