"""Tests for SummaryWorker (Qt) and build_summary_result helper."""

from __future__ import annotations

import time
from typing import Iterable, Iterator

import pytest

from mercury.agent.provider.llm_provider import (
    ChatMessage,
    LLMProvider,
    ProviderHTTPError,
)
from mercury.agent.summary.summary_agent import (
    SummaryAgent,
    SummaryRequest,
)
from mercury.agent.summary.summary_worker import (
    EMIT_INTERVAL_MS,
    SummaryJob,
    SummaryWorker,
    build_summary_result,
)


# -- Fakes --------------------------------------------------------------------


class StreamingProvider(LLMProvider):
    """Yields a fixed list of chunks, optionally pausing between them."""

    model = "stream-fake"

    def __init__(self, chunks: list[str], pause_seconds: float = 0.0) -> None:
        self._chunks = list(chunks)
        self._pause = pause_seconds

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        return "".join(self._chunks)

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        for c in self._chunks:
            if self._pause:
                time.sleep(self._pause)
            yield c


class RaisingProvider(LLMProvider):
    model = "boom"

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        raise ProviderHTTPError(500, "kapow")

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        raise ProviderHTTPError(500, "kapow")
        yield  # pragma: no cover (makes function a generator)


@pytest.fixture()
def request_obj() -> SummaryRequest:
    return SummaryRequest(
        entry_id="e1",
        title="hi",
        content="some article content",
    )


def _make_worker(agent: SummaryAgent, request: SummaryRequest) -> SummaryWorker:
    return SummaryWorker(agent, request, SummaryJob(job_id=1, entry_id=request.entry_id))


# -- Tests --------------------------------------------------------------------


def test_worker_emits_started_token_finished_in_order(qtbot, request_obj) -> None:
    agent = SummaryAgent(StreamingProvider(["Hel", "lo", " 世界"]))
    worker = _make_worker(agent, request_obj)

    events: list[str] = []
    worker.started.connect(lambda jid, eid: events.append(f"started:{eid}"))
    worker.token.connect(lambda jid, eid, c: events.append(f"token:{c}"))
    worker.finished.connect(
        lambda jid, eid, t, m, tr: events.append(f"finished:{t}:{m}:{tr}")
    )
    worker.failed.connect(lambda jid, eid, msg: events.append(f"failed:{msg}"))

    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.run()

    assert events[0] == "started:e1"
    assert events[-1].startswith("finished:Hello 世界:stream-fake@")
    assert events[-1].endswith(":False")  # truncated flag
    # At least one token event was emitted
    assert any(e.startswith("token:") for e in events)
    # No failures
    assert not any(e.startswith("failed") for e in events)


def test_worker_throttles_token_emissions(qtbot) -> None:
    """Many fast chunks should be coalesced into a smaller number of emits."""
    chunks = [f"c{i}" for i in range(40)]
    agent = SummaryAgent(StreamingProvider(chunks, pause_seconds=0.0))
    request = SummaryRequest(entry_id="e1", title="t", content="c")
    worker = _make_worker(agent, request)

    token_emits: list[str] = []
    worker.token.connect(lambda jid, eid, c: token_emits.append(c))

    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.run()

    # Without throttling we'd see 40 emissions; with 80ms gating we should see
    # markedly fewer. Be loose: anything < 40 proves throttling kicked in.
    assert len(token_emits) < len(chunks)
    # And the joined content still equals the input
    assert "".join(token_emits) == "".join(chunks)


def test_worker_emits_truncated_flag_on_long_content(qtbot) -> None:
    agent = SummaryAgent(StreamingProvider(["abc"]))
    big_request = SummaryRequest(
        entry_id="e2",
        title="t",
        content="X" * 50000,
        max_content_chars=2000,
    )
    worker = _make_worker(agent, big_request)

    seen: dict = {}
    worker.finished.connect(
        lambda jid, eid, t, m, tr: seen.update(model_id=m, truncated=tr)
    )
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.run()
    assert seen["truncated"] is True


def test_worker_failed_signal_on_provider_error(qtbot, request_obj) -> None:
    agent = SummaryAgent(RaisingProvider())
    worker = _make_worker(agent, request_obj)

    msgs: list[str] = []
    worker.failed.connect(lambda jid, eid, m: msgs.append(m))

    with qtbot.waitSignal(worker.failed, timeout=5000):
        worker.run()

    assert msgs and ("kapow" in msgs[0] or "500" in msgs[0])


def test_worker_cancel_emits_cancelled_signal(qtbot, request_obj) -> None:
    agent = SummaryAgent(StreamingProvider(["a", "b", "c"]))
    worker = _make_worker(agent, request_obj)
    worker.request_cancel()

    with qtbot.waitSignal(worker.cancelled, timeout=5000) as sig:
        worker.run()

    assert sig.args == [1, "e1"]


def test_worker_failed_on_empty_response(qtbot, request_obj) -> None:
    agent = SummaryAgent(StreamingProvider([]))
    worker = _make_worker(agent, request_obj)

    msgs: list[str] = []
    worker.failed.connect(lambda jid, eid, m: msgs.append(m))

    with qtbot.waitSignal(worker.failed, timeout=5000):
        worker.run()

    assert msgs and "empty" in msgs[0].lower()


# -- build_summary_result helper ---------------------------------------------


def test_build_summary_result_extracts_fingerprint() -> None:
    r = build_summary_result("e1", "text", "gpt-4o-mini@abcd1234")
    assert r.entry_id == "e1"
    assert r.text == "text"
    assert r.model_id == "gpt-4o-mini@abcd1234"
    assert r.template_fingerprint == "abcd1234"
    assert r.truncated is False


def test_build_summary_result_without_at_marker() -> None:
    """When model_id has no @, fingerprint should be empty (not the whole string)."""
    r = build_summary_result("e1", "text", "no-at-here")
    assert r.template_fingerprint == ""


def test_build_summary_result_carries_truncated_flag() -> None:
    r = build_summary_result("e1", "text", "m@fp", truncated=True)
    assert r.truncated is True
