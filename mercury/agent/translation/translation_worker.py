"""Qt worker for running TranslationAgent off the GUI thread."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from mercury.agent.provider.llm_provider import ProviderError
from mercury.agent.translation.translation_agent import (
    TranslationAgent,
    TranslationAgentError,
    TranslationRequest,
    TranslationResult,
    TranslationSegment,
)
from mercury.agent.translation.segmenter import segment_markdown

EMIT_INTERVAL_MS = 80


@dataclass(frozen=True)
class TranslationJob:
    """Identifies one translation run."""

    job_id: int
    entry_id: str


class TranslationWorker(QObject):
    """QObject worker with progress and terminal signals."""

    started = Signal(int, str, int)
    token = Signal(int, str, int, str, str, int, int)
    progress = Signal(int, str, int, int)
    finished = Signal(int, str, object)
    failed = Signal(int, str, str)
    cancelled = Signal(int, str)

    def __init__(
        self,
        agent: TranslationAgent,
        request: TranslationRequest,
        job: TranslationJob,
        completed_source_hashes: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._request = request
        self._job = job
        self._completed_source_hashes = completed_source_hashes or set()
        self._cancel = threading.Event()

    @Slot()
    def request_cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        job_id = self._job.job_id
        entry_id = self._job.entry_id
        try:
            source_segments = segment_markdown(self._request.content)
            if not source_segments:
                raise TranslationAgentError("No translatable segments found")
            total = len(source_segments)
            self.started.emit(job_id, entry_id, total)

            translated: list[TranslationSegment] = []
            for index, source in enumerate(source_segments, start=1):
                if source.source_hash in self._completed_source_hashes:
                    self.progress.emit(job_id, entry_id, index, total)
                    continue
                if self._cancel.is_set():
                    self.cancelled.emit(job_id, entry_id)
                    return
                if hasattr(self._agent, "prepare_segment_stream"):
                    segment = self._stream_one_segment(source, index, total)
                else:
                    segment = self._run_one_segment_for_legacy_agent(source)
                    self.token.emit(
                        job_id,
                        entry_id,
                        source.position,
                        source.source_text,
                        segment.trans_text,
                        index,
                        total,
                    )
                translated.append(segment)
                self.progress.emit(job_id, entry_id, index, total)

            if self._cancel.is_set():
                self.cancelled.emit(job_id, entry_id)
                return

            result = TranslationResult(
                entry_id=self._request.entry_id,
                target_language=self._request.target_language,
                segments=tuple(
                    TranslationSegment(
                        source_text=segment.source_text,
                        trans_text=segment.trans_text,
                        source_hash=segment.source_hash,
                        position=segment.position,
                    )
                    for segment in translated
                ),
                model_id=self._agent.build_model_id(),
                template_fingerprint=self._agent.template.fingerprint,
            )
        except _TranslationCancelled:
            return
        except ProviderError as exc:
            self.failed.emit(job_id, entry_id, str(exc))
            return
        except TranslationAgentError as exc:
            self.failed.emit(job_id, entry_id, str(exc))
            return
        except Exception as exc:
            self.failed.emit(job_id, entry_id, f"Unexpected: {exc}")
            return

        self.finished.emit(job_id, entry_id, result)

    def _stream_one_segment(self, source, current: int, total: int) -> TranslationSegment:
        job_id = self._job.job_id
        entry_id = self._job.entry_id
        meta, deltas = self._agent.prepare_segment_stream(self._request, source)
        del meta

        buffer: list[str] = []
        accumulated: list[str] = []
        last_emit = time.monotonic()

        for delta in deltas:
            if self._cancel.is_set():
                self.cancelled.emit(job_id, entry_id)
                raise _TranslationCancelled()
            if not delta:
                continue
            buffer.append(delta)
            accumulated.append(delta)
            now = time.monotonic()
            if (now - last_emit) * 1000 >= EMIT_INTERVAL_MS:
                self.token.emit(
                    job_id,
                    entry_id,
                    source.position,
                    source.source_text,
                    "".join(buffer),
                    current,
                    total,
                )
                buffer.clear()
                last_emit = now

        if buffer:
            self.token.emit(
                job_id,
                entry_id,
                source.position,
                source.source_text,
                "".join(buffer),
                current,
                total,
            )

        trans_text = "".join(accumulated).strip()
        if not trans_text:
            raise TranslationAgentError(
                f"Provider returned empty response for segment {source.position}"
            )
        return TranslationSegment(
            source_text=source.source_text,
            trans_text=trans_text,
            source_hash=source.source_hash,
            position=source.position,
        )

    def _run_one_segment_for_legacy_agent(self, source) -> TranslationSegment:
        partial_request = TranslationRequest(
            entry_id=self._request.entry_id,
            title=self._request.title,
            content=source.source_text,
            target_language=self._request.target_language,
        )
        partial_result = self._agent.run(partial_request)
        if not partial_result.segments:
            raise TranslationAgentError(
                f"Provider returned empty response for segment {source.position}"
            )
        segment = partial_result.segments[0]
        return TranslationSegment(
            source_text=source.source_text,
            trans_text=segment.trans_text,
            source_hash=source.source_hash,
            position=source.position,
        )


class _TranslationCancelled(Exception):
    """Internal sentinel used to unwind the streaming loop."""
