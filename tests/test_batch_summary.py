"""Tests for BatchSummaryWorker."""

from __future__ import annotations

from typing import Iterable, Iterator

import pytest

from agent.provider.llm_provider import (
    ChatMessage,
    LLMProvider,
    ProviderHTTPError,
)
from agent.summary.batch_worker import (
    BatchSummaryItem,
    BatchSummaryOutcome,
    BatchSummaryWorker,
)
from agent.summary.summary_agent import SummaryAgent, SummaryRequest


class ScriptedProvider(LLMProvider):
    """Returns scripted texts in order; raises a configured error on the Nth call."""

    model = "scripted"

    def __init__(self, texts: list[str], fail_at: set[int] | None = None) -> None:
        self._texts = list(texts)
        self._fail_at = fail_at or set()
        self._calls = 0

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        self._calls += 1
        if self._calls in self._fail_at:
            raise ProviderHTTPError(429, "rate limit")
        idx = self._calls - 1
        return self._texts[idx] if idx < len(self._texts) else "ok"

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        yield self.complete(messages)


def make_item(entry_id: str, title: str = "T", content: str = "body") -> BatchSummaryItem:
    return BatchSummaryItem(
        entry_id=entry_id,
        title=title,
        request=SummaryRequest(
            entry_id=entry_id, title=title, content=content, detail_level="default"
        ),
    )


def test_batch_runs_each_item_in_order(qtbot) -> None:
    provider = ScriptedProvider(["sum-A", "sum-B", "sum-C"])
    agent = SummaryAgent(provider)
    items = [make_item("a"), make_item("b"), make_item("c")]
    worker = BatchSummaryWorker(agent, items)

    outcomes: list[BatchSummaryOutcome] = []
    worker.item_done.connect(lambda o: outcomes.append(o))

    with qtbot.waitSignal(worker.finished, timeout=5000) as sig:
        worker.run()

    assert sig.args == [3, 0, 0]
    assert [o.entry_id for o in outcomes] == ["a", "b", "c"]
    assert [o.text for o in outcomes] == ["sum-A", "sum-B", "sum-C"]
    assert all(o.ok for o in outcomes)


def test_batch_continues_after_failure(qtbot) -> None:
    # Second call raises, others succeed
    provider = ScriptedProvider(["sum-A", "_", "sum-C"], fail_at={2})
    agent = SummaryAgent(provider)
    items = [make_item("a"), make_item("b"), make_item("c")]
    worker = BatchSummaryWorker(agent, items)

    outcomes: list[BatchSummaryOutcome] = []
    worker.item_done.connect(lambda o: outcomes.append(o))

    with qtbot.waitSignal(worker.finished, timeout=5000) as sig:
        worker.run()

    assert sig.args == [2, 1, 0]
    assert outcomes[1].ok is False
    assert "429" in outcomes[1].error or "rate limit" in outcomes[1].error
    # Other entries still succeed
    assert outcomes[0].ok and outcomes[0].text == "sum-A"
    assert outcomes[2].ok and outcomes[2].text == "sum-C"


def test_batch_skips_empty_content(qtbot) -> None:
    provider = ScriptedProvider(["sum-A"])
    agent = SummaryAgent(provider)
    items = [
        BatchSummaryItem(
            entry_id="empty",
            title="E",
            request=SummaryRequest(entry_id="empty", title="E", content="   "),
        ),
        make_item("a"),
    ]
    worker = BatchSummaryWorker(agent, items)

    outcomes: list[BatchSummaryOutcome] = []
    worker.item_done.connect(lambda o: outcomes.append(o))

    with qtbot.waitSignal(worker.finished, timeout=5000) as sig:
        worker.run()

    assert sig.args == [1, 0, 1]  # one ok, one skipped
    assert outcomes[0].skipped is True
    assert outcomes[1].ok is True


def test_batch_cancel_stops_remaining(qtbot) -> None:
    provider = ScriptedProvider(["A", "B", "C"])
    agent = SummaryAgent(provider)
    items = [make_item("a"), make_item("b"), make_item("c")]
    worker = BatchSummaryWorker(agent, items)
    # Pre-cancel: worker exits before processing the first item.
    worker.request_cancel()

    with qtbot.waitSignal(worker.cancelled, timeout=5000) as sig:
        worker.run()

    assert sig.args == [0, 0, 3]


def test_empty_provider_response_marked_failed(qtbot) -> None:
    provider = ScriptedProvider([""])
    agent = SummaryAgent(provider)
    items = [make_item("a")]
    worker = BatchSummaryWorker(agent, items)

    outcomes: list[BatchSummaryOutcome] = []
    worker.item_done.connect(lambda o: outcomes.append(o))

    with qtbot.waitSignal(worker.finished, timeout=5000) as sig:
        worker.run()

    assert sig.args == [0, 1, 0]
    assert outcomes[0].ok is False
