"""Markdown segment extraction for translation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

SEGMENTER_VERSION = "markdown-block-v1"


@dataclass(frozen=True)
class SourceSegment:
    """One source block to translate."""

    source_text: str
    position: int
    source_hash: str
    segmenter_version: str = SEGMENTER_VERSION


def segment_markdown(markdown: str) -> list[SourceSegment]:
    """Split Markdown into stable translatable blocks.

    The MVP keeps fenced code blocks intact and otherwise groups non-empty
    lines separated by blank lines. This is simple, deterministic, and works
    well for Reader canonical Markdown.
    """
    blocks = _split_blocks(markdown)
    return [
        SourceSegment(
            source_text=block,
            position=index,
            source_hash=hash_source_text(block),
        )
        for index, block in enumerate(blocks)
    ]


def hash_source_text(text: str) -> str:
    """Return a stable hash for cache invalidation."""
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    payload = f"{SEGMENTER_VERSION}\n{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _split_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            current.append(line)
            in_fence = not in_fence
            continue
        if not in_fence and not line.strip():
            _flush_block(blocks, current)
            continue
        current.append(line)

    _flush_block(blocks, current)
    return blocks


def _flush_block(blocks: list[str], current: list[str]) -> None:
    text = "\n".join(current).strip()
    current.clear()
    if text:
        blocks.append(text)
