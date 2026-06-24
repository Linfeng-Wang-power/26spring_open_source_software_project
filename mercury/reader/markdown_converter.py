"""Canonical Markdown conversion."""

from __future__ import annotations

import re
import unicodedata

from markdownify import markdownify as convert_html


def html_to_markdown(cleaned_html: str) -> str:
    """Convert cleaned reader HTML into canonical Markdown."""

    markdown = convert_html(
        cleaned_html,
        heading_style="ATX",
        bullets="-",
        strip=["span", "div"],
    )
    return _normalize_markdown(markdown)


def _normalize_markdown(markdown: str) -> str:
    markdown = _clean_text(markdown)
    lines = [line.rstrip() for line in markdown.strip().splitlines()]
    normalized: list[str] = []
    blank_seen = False

    for line in lines:
        if line:
            normalized.append(line)
            blank_seen = False
            continue
        if not blank_seen:
            normalized.append("")
            blank_seen = True

    return "\n".join(normalized).strip() + "\n"


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = text.replace("\ufffd", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text
