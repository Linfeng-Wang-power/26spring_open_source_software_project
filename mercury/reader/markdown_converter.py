"""Canonical Markdown conversion."""

from __future__ import annotations

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
