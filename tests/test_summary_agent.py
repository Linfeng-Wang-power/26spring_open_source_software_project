"""Tests for SummaryAgent end-to-end with a fake provider."""

from __future__ import annotations

from typing import Iterable, Iterator

import pytest

from agent.provider.llm_provider import (
    ChatMessage,
    LLMProvider,
    ProviderHTTPError,
)
from agent.summary.summary_agent import (
    SummaryAgent,
    SummaryAgentError,
    SummaryRequest,
)


class FakeProvider(LLMProvider):
    """In-memory provider used to assert agent behavior without HTTP."""

    def __init__(
        self,
        *,
        complete_text: str = "",
        stream_chunks: list[str] | None = None,
        raise_on: str | None = None,
        model: str = "fake-1",
    ) -> None:
        self.complete_text = complete_text
        self.stream_chunks = stream_chunks or []
        self.raise_on = raise_on
        self.model = model
        self.last_messages: list[ChatMessage] = []

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        self.last_messages = list(messages)
        if self.raise_on == "complete":
            raise ProviderHTTPError(500, "boom")
        return self.complete_text

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        self.last_messages = list(messages)
        if self.raise_on == "stream":
            raise ProviderHTTPError(429, "rate limited")
        for chunk in self.stream_chunks:
            yield chunk


@pytest.fixture()
def request_obj() -> SummaryRequest:
    return SummaryRequest(
        entry_id="e1",
        title="Hello",
        content="World content",
        target_language="zh-CN",
        detail_level="short",
    )


def test_run_returns_full_text(request_obj: SummaryRequest) -> None:
    provider = FakeProvider(complete_text="  这是摘要  ")
    agent = SummaryAgent(provider)
    result = agent.run(request_obj)
    assert result.text == "这是摘要"
    assert result.entry_id == "e1"
    assert result.model_id.startswith("fake-1@")
    assert result.template_fingerprint
    # Variables made it into the prompt.
    full = " ".join(m.content for m in provider.last_messages)
    assert "World content" in full
    assert "zh-CN" in full
    assert "short" in full


def test_stream_assembles_chunks(request_obj: SummaryRequest) -> None:
    provider = FakeProvider(stream_chunks=["这", "是", "摘要"])
    agent = SummaryAgent(provider)
    seen: list[str] = []
    result = agent.stream(request_obj, on_token=seen.append)
    assert result.text == "这是摘要"
    assert seen == ["这", "是", "摘要"]


def test_stream_empty_response_raises(request_obj: SummaryRequest) -> None:
    provider = FakeProvider(stream_chunks=[])
    agent = SummaryAgent(provider)
    with pytest.raises(SummaryAgentError):
        agent.stream(request_obj)


def test_invalid_detail_level_raises() -> None:
    provider = FakeProvider(complete_text="x")
    agent = SummaryAgent(provider)
    bad = SummaryRequest(
        entry_id="e1", title="t", content="c", detail_level="medium"
    )
    with pytest.raises(SummaryAgentError):
        agent.run(bad)


def test_provider_error_propagates(request_obj: SummaryRequest) -> None:
    provider = FakeProvider(raise_on="stream")
    agent = SummaryAgent(provider)
    with pytest.raises(ProviderHTTPError):
        agent.stream(request_obj)


def test_stream_iter_yields_raw_deltas(request_obj: SummaryRequest) -> None:
    provider = FakeProvider(stream_chunks=["a", "b", "c"])
    agent = SummaryAgent(provider)
    assert list(agent.stream_iter(request_obj)) == ["a", "b", "c"]


def test_target_language_passes_through() -> None:
    provider = FakeProvider(complete_text="ok")
    agent = SummaryAgent(provider)
    req = SummaryRequest(
        entry_id="e2",
        title="T",
        content="C",
        target_language="en",
        detail_level="default",
    )
    agent.run(req)
    full = " ".join(m.content for m in provider.last_messages)
    assert "en" in full
    assert "default" in full
