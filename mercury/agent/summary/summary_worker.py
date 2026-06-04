"""Qt worker that runs the SummaryAgent off the GUI thread.

Streaming tokens are buffered and flushed at most every ``EMIT_INTERVAL_MS``
milliseconds so the GUI is never overwhelmed by SSE chunk frequency.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from mercury.agent.provider.llm_provider import ProviderError
from mercury.agent.summary.summary_agent import (
    SummaryAgent,
    SummaryAgentError,
    SummaryRequest,
    SummaryResult,
)

EMIT_INTERVAL_MS = 80


@dataclass(frozen=True)
class SummaryJob:
    """Identifies one summary run so stale results can be ignored after entry switch."""

    job_id: int
    entry_id: str


class SummaryWorker(QObject):
    """QObject worker; move to a QThread and call ``run`` via Qt signals.

    Signals (all carry job_id + entry_id so the GUI can ignore stale jobs):

    - ``started(job_id, entry_id)``       -- before the network call
    - ``token(job_id, entry_id, chunk)``  -- buffered streaming text
    - ``finished(job_id, entry_id, full_text, model_id, truncated)``
    - ``failed(job_id, entry_id, message)``
    - ``cancelled(job_id, entry_id)``
    """

    started = Signal(int, str)
    token = Signal(int, str, str)
    # full_text, model_id, truncated_flag
    finished = Signal(int, str, str, str, bool)
    failed = Signal(int, str, str)
    cancelled = Signal(int, str)

    def __init__(
        self,
        agent: SummaryAgent,
        request: SummaryRequest,
        job: SummaryJob,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._request = request
        self._job = job
        # threading.Event provides a real cross-thread synchronization
        # primitive; a bare bool would rely on CPython's GIL semantics and
        # break on free-threaded Python or alternative implementations.
        self._cancel = threading.Event()

    @Slot()
    def request_cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        job_id = self._job.job_id
        entry_id = self._job.entry_id
        self.started.emit(job_id, entry_id)

        buffer: list[str] = []
        last_emit = time.monotonic()
        accumulated: list[str] = []

        try:
            meta, deltas = self._agent.prepare_stream(self._request)
            for delta in deltas:
                if self._cancel.is_set():
                    self.cancelled.emit(job_id, entry_id)
                    return
                if not delta:
                    continue
                buffer.append(delta)
                accumulated.append(delta)
                now = time.monotonic()
                if (now - last_emit) * 1000 >= EMIT_INTERVAL_MS:
                    self.token.emit(job_id, entry_id, "".join(buffer))
                    buffer.clear()
                    last_emit = now
        except ProviderError as exc:
            self.failed.emit(job_id, entry_id, str(exc))
            return
        except SummaryAgentError as exc:
            self.failed.emit(job_id, entry_id, str(exc))
            return
        except Exception as exc:
            self.failed.emit(job_id, entry_id, f"Unexpected: {exc}")
            return

        if buffer:
            self.token.emit(job_id, entry_id, "".join(buffer))

        full_text = "".join(accumulated).strip()
        if not full_text:
            self.failed.emit(job_id, entry_id, "Provider returned empty response")
            return

        if self._cancel.is_set():
            self.cancelled.emit(job_id, entry_id)
            return

        self.finished.emit(
            job_id, entry_id, full_text, meta.model_id, meta.truncated
        )


def build_summary_result(
    entry_id: str, full_text: str, model_id: str, truncated: bool = False
) -> SummaryResult:
    """Helper for tests / GUI to wrap the worker's terminal data.

    ``model_id`` is expected to follow the ``model@fingerprint`` shape; if it
    has no ``@``, ``template_fingerprint`` is left empty rather than
    inheriting the whole string.
    """
    fingerprint = model_id.split("@", 1)[1] if "@" in model_id else ""
    return SummaryResult(
        entry_id=entry_id,
        text=full_text,
        model_id=model_id,
        template_fingerprint=fingerprint,
        truncated=truncated,
    )
