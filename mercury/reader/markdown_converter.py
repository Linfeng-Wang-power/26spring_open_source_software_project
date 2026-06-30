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
    markdown = _dedent_prose_blocks(markdown)
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


def _dedent_prose_blocks(markdown: str) -> str:
    """Undo accidental indented-code markdown for ordinary article prose."""
    lines = markdown.splitlines(keepends=True)
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _is_indented_or_blank(line):
            normalized.append(line)
            index += 1
            continue

        run: list[str] = []
        while index < len(lines) and _is_indented_or_blank(lines[index]):
            run.append(lines[index])
            index += 1
        if not any(item.strip() for item in run):
            normalized.extend(run)
            continue

        candidate = "".join(_dedent_line(item) for item in run)
        if _looks_like_prose(candidate):
            normalized.append(candidate)
        else:
            normalized.extend(run)
    return "".join(normalized)


def _is_indented_or_blank(line: str) -> bool:
    return not line.strip() or line.startswith(("    ", "\t"))


def _dedent_line(line: str) -> str:
    if line.startswith("    "):
        return line[4:]
    if line.startswith("\t"):
        return line[1:]
    return line


def _looks_like_prose(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if any(marker in lowered for marker in ("def ", "class ", "import ", "function ", "{", "};", "</")):
        return False
    words = stripped.split()
    sentence_marks = sum(stripped.count(mark) for mark in ".?!。！？")
    has_article_shape = (
        "\n\n" in stripped
        or ":" in stripped
        or any(line.strip().startswith(("http://", "https://")) for line in stripped.splitlines())
    )
    return len(words) >= 8 and (sentence_marks >= 1 or has_article_shape)


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
