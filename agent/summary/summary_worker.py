"""Qt worker that runs the SummaryAgent off the GUI thread.

Streaming tokens are buffered and flushed at most every ``EMIT_INTERVAL_MS``
milliseconds so the GUI is never overwhelmed by SSE chunk frequency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from agent.provider.llm_provider import ProviderError
from agent.summary.summary_agent import (
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
    - ``finished(job_id, entry_id, full_text, model_id)``
    - ``failed(job_id, entry_id, message)``
    - ``cancelled(job_id, entry_id)``
    """

    started = Signal(int, str)
    token = Signal(int, str, str)
    finished = Signal(int, str, str, str)
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
        self._cancel_requested = False

    # The cancel flag is set from the GUI thread but read by the worker thread.
    # Python's GIL makes this scalar read/write safe enough for an MVP without
    # a QMutex; the worst case is one extra token after cancel.
    @Slot()
    def request_cancel(self) -> None:
        self._cancel_requested = True

    @Slot()
    def run(self) -> None:
        job_id = self._job.job_id
        entry_id = self._job.entry_id
        self.started.emit(job_id, entry_id)

        buffer: list[str] = []
        last_emit = time.monotonic()
        accumulated: list[str] = []

        try:
            for delta in self._agent.stream_iter(self._request):
                if self._cancel_requested:
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

        if self._cancel_requested:
            self.cancelled.emit(job_id, entry_id)
            return

        model_id = f"{getattr(self._agent._provider, 'model', 'unknown')}@{self._agent.template.fingerprint}"
        self.finished.emit(job_id, entry_id, full_text, model_id)


def build_summary_result(
    entry_id: str, full_text: str, model_id: str
) -> SummaryResult:
    """Helper for tests / GUI to wrap the worker's terminal data."""
    fingerprint = model_id.split("@")[-1] if "@" in model_id else ""
    return SummaryResult(
        entry_id=entry_id,
        text=full_text,
        model_id=model_id,
        template_fingerprint=fingerprint,
    )
