"""Qt worker for running TranslationAgent off the GUI thread."""

from __future__ import annotations

import threading
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


@dataclass(frozen=True)
class TranslationJob:
    """Identifies one translation run."""

    job_id: int
    entry_id: str


class TranslationWorker(QObject):
    """QObject worker with progress and terminal signals."""

    started = Signal(int, str, int)
    progress = Signal(int, str, int, int)
    finished = Signal(int, str, object)
    failed = Signal(int, str, str)
    cancelled = Signal(int, str)

    def __init__(
        self,
        agent: TranslationAgent,
        request: TranslationRequest,
        job: TranslationJob,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._request = request
        self._job = job
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
                if self._cancel.is_set():
                    self.cancelled.emit(job_id, entry_id)
                    return
                partial_request = TranslationRequest(
                    entry_id=self._request.entry_id,
                    title=self._request.title,
                    content=source.source_text,
                    target_language=self._request.target_language,
                )
                partial_result = self._agent.run(partial_request)
                translated.extend(partial_result.segments)
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
                        position=index,
                    )
                    for index, segment in enumerate(translated)
                ),
                model_id=self._agent.build_model_id(),
                template_fingerprint=self._agent.template.fingerprint,
            )
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
