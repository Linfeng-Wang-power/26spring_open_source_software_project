"""Readable article extraction."""

from __future__ import annotations

from bs4 import BeautifulSoup
from readability import Document

from mercury.reader.models import ReadabilityResult

NO_TITLE = "[no-title]"


def extract_readable_html(source_html: str) -> ReadabilityResult:
    """Extract main article HTML using readability-lxml."""

    document = Document(source_html)
    title = _best_title(source_html, document)
    content_html = _best_content_html(source_html, document.summary(html_partial=True))
    return ReadabilityResult(title=title, content_html=content_html)


def _best_title(source_html: str, document: Document) -> str:
    readability_title = (document.short_title() or document.title() or "").strip()
    if _is_usable_title(readability_title):
        return readability_title

    soup = BeautifulSoup(source_html, "html.parser")
    for tag in (
        soup.find("meta", {"property": "og:title"}),
        soup.find("meta", {"name": "twitter:title"}),
        soup.find("h1"),
        soup.find("title"),
    ):
        if tag is None:
            continue
        value = tag.get("content", "") if tag.name == "meta" else tag.get_text(" ", strip=True)
        value = value.strip()
        if _is_usable_title(value):
            return value

    return "Untitled"


def _is_usable_title(title: str) -> bool:
    normalized = title.strip().lower()
    return bool(normalized and normalized != NO_TITLE)


def _best_content_html(source_html: str, readability_html: str) -> str:
    if _text_length(readability_html) >= 300:
        return readability_html

    soup = BeautifulSoup(source_html, "html.parser")
    candidates = []
    candidates.extend(soup.find_all("article"))
    candidates.extend(soup.find_all("main"))
    candidates.extend(soup.find_all(attrs={"role": "main"}))

    best = max(candidates, key=lambda tag: _text_length(str(tag)), default=None)
    if best is not None and _text_length(str(best)) > _text_length(readability_html):
        return str(best)

    return readability_html


def _text_length(html: str) -> int:
    return len(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
