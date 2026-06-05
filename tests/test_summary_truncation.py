"""Tests for content truncation in the summary agent."""

from __future__ import annotations

from typing import Iterable, Iterator

import pytest

from mercury.agent.provider.llm_provider import ChatMessage, LLMProvider
from mercury.agent.summary.summary_agent import (
    DEFAULT_MAX_CONTENT_CHARS,
    SummaryAgent,
    SummaryRequest,
    TRUNCATION_NOTICE,
    truncate_content,
)


class CapturingProvider(LLMProvider):
    """Records messages it receives so tests can assert on the rendered prompt."""

    model = "fake-1"

    def __init__(self) -> None:
        self.last_messages: list[ChatMessage] = []

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        self.last_messages = list(messages)
        return "ok"

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        self.last_messages = list(messages)
        yield "ok"


def test_truncate_keeps_short_text_unchanged() -> None:
    text = "abc"
    out, truncated = truncate_content(text, 100)
    assert out == "abc"
    assert truncated is False


def test_truncate_zero_or_negative_disables() -> None:
    text = "x" * 1000
    assert truncate_content(text, 0) == (text, False)
    assert truncate_content(text, -1) == (text, False)


def test_truncate_long_text_includes_notice_and_tail() -> None:
    head = "H" * 5000
    tail = "T" * 5000
    text = head + tail
    out, truncated = truncate_content(text, max_chars=200)
    assert truncated is True
    assert TRUNCATION_NOTICE.strip() in out
    # Both head signal and tail signal should be present
    assert "H" in out and "T" in out
    # Result is bounded by max_chars (allow small slack for the notice)
    assert len(out) <= 200 + len(TRUNCATION_NOTICE)


def test_truncate_head_dominates() -> None:
    text = "A" * 100 + "B" * 100
    out, truncated = truncate_content(text, max_chars=120)
    assert truncated is True
    a_count = out.count("A")
    b_count = out.count("B")
    # We allocate ~60% to head, ~40% to tail
    assert a_count > b_count


def test_agent_passes_truncated_content_to_provider() -> None:
    provider = CapturingProvider()
    agent = SummaryAgent(provider)
    big_content = "X" * 50000
    req = SummaryRequest(
        entry_id="e1",
        title="Big",
        content=big_content,
        max_content_chars=2000,
    )
    result = agent.run(req)
    assert result.truncated is True

    user_content = next(m.content for m in provider.last_messages if m.role == "user")
    assert TRUNCATION_NOTICE.strip() in user_content
    # Sent prompt is roughly within the limit (template adds a small wrapper)
    assert len(user_content) <= 2000 + 500


def test_agent_does_not_mark_short_content_truncated() -> None:
    provider = CapturingProvider()
    agent = SummaryAgent(provider)
    req = SummaryRequest(
        entry_id="e1",
        title="Small",
        content="just a few words",
    )
    result = agent.run(req)
    assert result.truncated is False


def test_default_budget_is_reasonable() -> None:
    assert DEFAULT_MAX_CONTENT_CHARS >= 4000
