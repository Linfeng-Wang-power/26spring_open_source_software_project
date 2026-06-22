"""Tests for TranslationAgent with a fake provider."""

from __future__ import annotations

from typing import Iterable, Iterator

import pytest

from mercury.agent.provider.llm_provider import ChatMessage, ProviderError
from mercury.agent.translation.translation_agent import (
    TranslationAgent,
    TranslationAgentError,
    TranslationRequest,
)


class FakeProvider:
    model = "fake-translator"

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        raise_on_complete: bool = False,
    ) -> None:
        self.responses = responses or ["译文"]
        self.raise_on_complete = raise_on_complete
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        if self.raise_on_complete:
            raise ProviderError("upstream failed")
        materialized = list(messages)
        self.calls.append(materialized)
        index = len(self.calls) - 1
        return self.responses[index] if index < len(self.responses) else self.responses[-1]

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        yield from ()


@pytest.fixture()
def request_obj() -> TranslationRequest:
    return TranslationRequest(
        entry_id="e1",
        title="Hello",
        content="First paragraph.\n\nSecond paragraph.",
        target_language="zh-CN",
    )


def test_translate_multiple_segments(request_obj: TranslationRequest) -> None:
    provider = FakeProvider(["第一段译文", "第二段译文"])
    agent = TranslationAgent(provider)

    result = agent.run(request_obj)

    assert result.entry_id == "e1"
    assert result.target_language == "zh-CN"
    assert result.model_id == f"fake-translator@{agent.template.fingerprint}"
    assert result.template_fingerprint == agent.template.fingerprint
    assert [s.trans_text for s in result.segments] == ["第一段译文", "第二段译文"]
    assert [s.position for s in result.segments] == [0, 1]
    assert len(provider.calls) == 2


def test_prompt_receives_target_language_and_segment(request_obj: TranslationRequest) -> None:
    provider = FakeProvider(["ok", "ok"])
    agent = TranslationAgent(provider)

    agent.run(request_obj)

    full_prompt = "\n".join(message.content for message in provider.calls[0])
    assert "zh-CN" in full_prompt
    assert "First paragraph." in full_prompt
    assert "Second paragraph." not in full_prompt


def test_empty_provider_response_is_rejected(request_obj: TranslationRequest) -> None:
    provider = FakeProvider(["   "])
    agent = TranslationAgent(provider)

    with pytest.raises(TranslationAgentError, match="empty response"):
        agent.run(request_obj)


def test_provider_error_propagates(request_obj: TranslationRequest) -> None:
    provider = FakeProvider(raise_on_complete=True)
    agent = TranslationAgent(provider)

    with pytest.raises(ProviderError):
        agent.run(request_obj)


def test_request_rejects_empty_content() -> None:
    with pytest.raises(TranslationAgentError):
        TranslationRequest(entry_id="e1", title="x", content="")
