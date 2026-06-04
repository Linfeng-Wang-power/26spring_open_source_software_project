"""End-to-end integration test for the Summary Agent full pipeline.

Exercises: template -> agent -> worker (Qt signals) -> storage -> restore.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable, Iterator

import pytest

# ── Agent layer ──────────────────────────────────────────────────────────────
from agent.provider.llm_provider import ChatMessage, LLMProvider
from agent.prompts.template_renderer import load_template, render_template
from agent.summary.summary_agent import (
    SummaryAgent,
    SummaryAgentError,
    SummaryRequest,
)
from agent.summary.summary_worker import SummaryJob, SummaryWorker

# ── Storage layer ────────────────────────────────────────────────────────────
from mercury_storage import SummaryStore, apply_migrations, get_connection

# ── PySide6 (Qt) ────────────────────────────────────────────────────────────
from PySide6.QtCore import QThread, QObject, Signal


# ─── Fake provider ──────────────────────────────────────────────────────────

class FakeStreamingProvider(LLMProvider):
    """Simulates an SSE-style streaming provider with configurable chunks."""

    def __init__(self, chunks: list[str], model: str = "fake-gpt-4o") -> None:
        self._chunks = chunks
        self.model = model
        self.call_count = 0
        self.last_messages: list[ChatMessage] = []

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        self.last_messages = list(messages)
        self.call_count += 1
        return "".join(self._chunks)

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        self.last_messages = list(messages)
        self.call_count += 1
        for c in self._chunks:
            yield c


# ─── Fixtures ───────────────────────────────────────────────────────────────

ARTICLE_TITLE = "Understanding Rust's Ownership Model"
ARTICLE_CONTENT = """\
Rust introduces a unique ownership system that ensures memory safety without
a garbage collector. Each value in Rust has a single owner, and when the owner
goes out of scope, the value is automatically dropped. References allow you to
borrow values without taking ownership, but Rust enforces strict rules: you can
have either one mutable reference or any number of immutable references at a
time. This prevents data races at compile time, making concurrent programming
significantly safer. The borrow checker is the compiler component responsible
for enforcing these rules, and while it can feel restrictive at first, it
guides developers toward correct and efficient code patterns.
"""


@pytest.fixture()
def request_obj() -> SummaryRequest:
    return SummaryRequest(
        entry_id="entry-rust-001",
        title=ARTICLE_TITLE,
        content=ARTICLE_CONTENT,
        target_language="zh-CN",
        detail_level="default",
    )


@pytest.fixture()
def streaming_provider() -> FakeStreamingProvider:
    return FakeStreamingProvider(
        chunks=[
            "Rust 的",
            "所有权模型",
            "通过单一所有者",
            "和借用规则",
            "实现了无 GC 的",
            "内存安全。",
            "编译器中的",
            "借用检查器",
            "在编译期",
            "防止数据竞争，",
            "使并发编程",
            "更加安全。",
        ]
    )


@pytest.fixture()
def db_store(tmp_path):
    db = tmp_path / "integration_test.db"
    apply_migrations(db)
    conn = get_connection(db)
    # Seed feed + entry for FK
    conn.execute(
        "INSERT INTO feeds (feed_id, title, url, added_at) VALUES (?,?,?,?)",
        ("f1", "Tech Blog", "https://example.com/feed", "2025-01-01"),
    )
    conn.execute(
        "INSERT INTO entries (entry_id, feed_id, stable_id, title, url, published, summary)"
        " VALUES (?,?,?,?,?,?,?)",
        ("entry-rust-001", "f1", "s1", ARTICLE_TITLE, "https://example.com/rust", "2025-06-01", ""),
    )
    conn.commit()
    yield SummaryStore(conn)
    conn.close()


# ─── Test 1: Template -> render produces valid prompt ──────────────────────

class TestTemplateRendering:
    def test_summary_template_renders_article(self) -> None:
        tpl = load_template("summary.default")
        rendered = render_template(tpl, {
            "target_language": "zh-CN",
            "detail_level": "default",
            "title": ARTICLE_TITLE,
            "content": ARTICLE_CONTENT,
        })
        assert len(rendered.messages) == 2
        system = rendered.messages[0]
        user = rendered.messages[1]
        assert system.role == "system"
        assert "zh-CN" in system.content
        assert "default" in system.content
        assert user.role == "user"
        assert ARTICLE_TITLE in user.content
        assert "ownership" in user.content.lower() or "Ownership" in user.content
        assert rendered.template_fingerprint == tpl.fingerprint


# ─── Test 2: Agent streaming assembles correct result ──────────────────────

class TestAgentStreaming:
    def test_stream_produces_coherent_summary(
        self, streaming_provider: FakeStreamingProvider, request_obj: SummaryRequest
    ) -> None:
        agent = SummaryAgent(streaming_provider)
        tokens_seen: list[str] = []
        result = agent.stream(request_obj, on_token=tokens_seen.append)

        assert result.entry_id == "entry-rust-001"
        assert "Rust" in result.text
        assert "所有权" in result.text or "内存安全" in result.text
        assert result.model_id.startswith("fake-gpt-4o@")
        assert result.template_fingerprint
        assert streaming_provider.call_count == 1
        assert len(tokens_seen) == 12  # 12 chunks

    def test_run_non_streaming(
        self, streaming_provider: FakeStreamingProvider, request_obj: SummaryRequest
    ) -> None:
        agent = SummaryAgent(streaming_provider)
        result = agent.run(request_obj)
        assert "Rust" in result.text
        assert streaming_provider.call_count == 1

    def test_stream_iter_raw(
        self, streaming_provider: FakeStreamingProvider, request_obj: SummaryRequest
    ) -> None:
        agent = SummaryAgent(streaming_provider)
        deltas = list(agent.stream_iter(request_obj))
        assert deltas == streaming_provider._chunks


# ─── Test 3: Worker emits Qt signals in correct order ──────────────────────

class TestWorkerSignals:
    def test_worker_emits_started_token_finished(
        self, streaming_provider: FakeStreamingProvider, request_obj: SummaryRequest, qtbot
    ) -> None:
        agent = SummaryAgent(streaming_provider)
        job = SummaryJob(job_id=1, entry_id="entry-rust-001")
        worker = SummaryWorker(agent, request_obj, job)

        events: list[str] = []

        worker.started.connect(lambda jid, eid: events.append(f"started:{eid}"))
        worker.token.connect(lambda jid, eid, chunk: events.append(f"token:{len(chunk)}"))
        worker.finished.connect(
            lambda jid, eid, text, mid: events.append(f"finished:{eid}:{len(text)}:{mid}")
        )
        worker.failed.connect(lambda jid, eid, msg: events.append(f"failed:{msg}"))

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.run()

        # First event must be started
        assert events[0] == "started:entry-rust-001"
        # Last event must be finished
        assert events[-1].startswith("finished:entry-rust-001:")
        # No failures
        assert not any(e.startswith("failed") for e in events)
        # There should be at least one token event
        token_events = [e for e in events if e.startswith("token:")]
        assert len(token_events) >= 1

    def test_worker_cancel_stops_mid_stream(
        self, request_obj: SummaryRequest, qtbot
    ) -> None:
        """If cancel is requested during streaming, worker emits cancelled."""

        class SlowProvider(LLMProvider):
            model = "slow"

            def complete(self, messages):
                return "x"

            def stream(self, messages):
                for i in range(100):
                    yield f"chunk-{i}-"

        agent = SummaryAgent(SlowProvider())
        job = SummaryJob(job_id=2, entry_id="entry-rust-001")
        worker = SummaryWorker(agent, request_obj, job)
        # Pre-cancel so the first iteration triggers the check
        worker.request_cancel()

        events: list[str] = []
        worker.cancelled.connect(lambda jid, eid: events.append("cancelled"))
        worker.finished.connect(lambda *a: events.append("finished"))

        with qtbot.waitSignal(worker.cancelled, timeout=5000):
            worker.run()

        assert "cancelled" in events
        assert "finished" not in events


# ─── Test 4: Store persists and restores summary ──────────────────────────

class TestStorePersistence:
    def test_save_get_delete_lifecycle(self, db_store: SummaryStore) -> None:
        assert db_store.get("entry-rust-001") is None

        db_store.save_result("entry-rust-001", "Rust 所有权模型的摘要。", "fake-gpt-4o@abc")
        text = db_store.get("entry-rust-001")
        assert text == "Rust 所有权模型的摘要。"

        meta = db_store.get_metadata("entry-rust-001")
        assert meta["model_id"] == "fake-gpt-4o@abc"
        assert meta["created_at"]

        db_store.delete("entry-rust-001")
        assert db_store.get("entry-rust-001") is None

    def test_overwrite_preserves_latest(self, db_store: SummaryStore) -> None:
        db_store.save_result("entry-rust-001", "第一版摘要", "v1")
        db_store.save_result("entry-rust-001", "第二版摘要", "v2")
        assert db_store.get("entry-rust-001") == "第二版摘要"
        assert db_store.get_metadata("entry-rust-001")["model_id"] == "v2"

    def test_empty_rejected(self, db_store: SummaryStore) -> None:
        db_store.save_result("entry-rust-001", "好摘要", "v1")
        with pytest.raises(ValueError):
            db_store.save_result("entry-rust-001", "", "v2")
        assert db_store.get("entry-rust-001") == "好摘要"


# ─── Test 5: Full pipeline (agent -> store round-trip) ────────────────────

class TestFullPipeline:
    def test_agent_result_persisted_and_restored(
        self, streaming_provider: FakeStreamingProvider, request_obj: SummaryRequest, db_store: SummaryStore
    ) -> None:
        # Step 1: Run the agent
        agent = SummaryAgent(streaming_provider)
        result = agent.run(request_obj)

        # Step 2: Persist to store (as the GUI would do in _on_summary_finished)
        db_store.save_result(result.entry_id, result.text, result.model_id)

        # Step 3: Simulate entry switch -> restore from store
        restored = db_store.get("entry-rust-001")
        assert restored is not None
        assert restored == result.text
        assert "Rust" in restored

        # Step 4: Metadata is intact
        meta = db_store.get_metadata("entry-rust-001")
        assert meta["model_id"].startswith("fake-gpt-4o@")

    def test_worker_finished_result_persisted(
        self, streaming_provider, request_obj, db_store, qtbot
    ) -> None:
        """Worker finishes -> GUI handler persists -> can be restored."""
        agent = SummaryAgent(streaming_provider)
        job = SummaryJob(job_id=99, entry_id="entry-rust-001")
        worker = SummaryWorker(agent, request_obj, job)

        finished_data = {}

        def on_finished(jid, eid, full_text, model_id):
            finished_data["text"] = full_text
            finished_data["model_id"] = model_id
            db_store.save_result(eid, full_text, model_id)

        worker.finished.connect(on_finished)

        with qtbot.waitSignal(worker.finished, timeout=5000):
            worker.run()

        assert finished_data["text"]
        assert "Rust" in finished_data["text"]
        # Store round-trip
        assert db_store.get("entry-rust-001") == finished_data["text"]
