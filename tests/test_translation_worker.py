"""Tests for TranslationWorker streaming signals."""

from __future__ import annotations

import time
from typing import Iterable, Iterator

from mercury.agent.provider.llm_provider import ChatMessage, LLMProvider
from mercury.agent.translation.translation_agent import (
    TranslationAgent,
    TranslationRequest,
)
from mercury.agent.translation.translation_worker import (
    TranslationJob,
    TranslationWorker,
)


class StreamingProvider(LLMProvider):
    model = "translation-stream-fake"

    def __init__(self, chunks: list[str], pause_seconds: float = 0.0) -> None:
        self._chunks = list(chunks)
        self._pause = pause_seconds

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        return "".join(self._chunks)

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        for chunk in self._chunks:
            if self._pause:
                time.sleep(self._pause)
            yield chunk


def test_translation_worker_emits_streaming_tokens(qtbot) -> None:
    request = TranslationRequest(
        entry_id="e1",
        title="Hello",
        content="First paragraph.",
        target_language="zh-CN",
    )
    agent = TranslationAgent(StreamingProvider(["first ", "translated"]))
    worker = TranslationWorker(agent, request, TranslationJob(1, "e1"))

    tokens: list[str] = []
    progress: list[tuple[int, int]] = []
    worker.token.connect(
        lambda jid, eid, pos, src, chunk, current, total: tokens.append(chunk)
    )
    worker.progress.connect(
        lambda jid, eid, current, total: progress.append((current, total))
    )

    with qtbot.waitSignal(worker.finished, timeout=5000) as finished:
        worker.run()

    result = finished.args[2]
    assert "".join(tokens) == "first translated"
    assert progress == [(1, 1)]
    assert result.segments[0].trans_text == "first translated"


def test_translation_worker_cancel_emits_cancelled(qtbot) -> None:
    request = TranslationRequest(
        entry_id="e1",
        title="Hello",
        content="First paragraph.",
        target_language="zh-CN",
    )
    agent = TranslationAgent(StreamingProvider(["first", " translated"]))
    worker = TranslationWorker(agent, request, TranslationJob(1, "e1"))
    worker.request_cancel()

    with qtbot.waitSignal(worker.cancelled, timeout=5000) as cancelled:
        worker.run()

    assert cancelled.args == [1, "e1"]
