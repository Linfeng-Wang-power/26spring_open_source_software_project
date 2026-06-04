"""Qt worker for running multiple summaries one at a time.

Streaming is disabled for batch jobs so we can churn through entries
quickly without UI thrash. Each entry's outcome is emitted on the
``item_done`` signal; ``finished`` carries totals.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from agent.provider.llm_provider import ProviderError
from agent.summary.summary_agent import (
    SummaryAgent,
    SummaryAgentError,
    SummaryRequest,
)


@dataclass(frozen=True)
class BatchSummaryItem:
    """One unit of work in a batch."""

    entry_id: str
    title: str
    request: SummaryRequest


@dataclass(frozen=True)
class BatchSummaryOutcome:
    """Per-item terminal state for the GUI to display."""

    entry_id: str
    title: str
    ok: bool
    text: str = ""
    model_id: str = ""
    error: str = ""
    truncated: bool = False
    skipped: bool = False


class BatchSummaryWorker(QObject):
    """Runs a list of summary requests sequentially.

    Signals:
    - ``progress(current_index, total, title)`` -- emitted before each item
    - ``item_done(outcome)``                    -- per-item result
    - ``finished(success_count, fail_count, skipped_count)``
    - ``cancelled(success_count, fail_count, skipped_count)``
    """

    progress = Signal(int, int, str)
    item_done = Signal(object)
    finished = Signal(int, int, int)
    cancelled = Signal(int, int, int)

    def __init__(self, agent: SummaryAgent, items: list[BatchSummaryItem]) -> None:
        super().__init__()
        self._agent = agent
        self._items = items
        self._cancel = False

    @Slot()
    def request_cancel(self) -> None:
        self._cancel = True

    @Slot()
    def run(self) -> None:
        success = 0
        fail = 0
        skipped = 0
        total = len(self._items)
        for idx, item in enumerate(self._items, start=1):
            if self._cancel:
                # Remaining items count as skipped so the totals line up.
                skipped += total - (idx - 1)
                self.cancelled.emit(success, fail, skipped)
                return

            self.progress.emit(idx, total, item.title)
            outcome = self._run_one(item)
            self.item_done.emit(outcome)
            if outcome.ok:
                success += 1
            elif outcome.skipped:
                skipped += 1
            else:
                fail += 1

        self.finished.emit(success, fail, skipped)

    def _run_one(self, item: BatchSummaryItem) -> BatchSummaryOutcome:
        if not item.request.content.strip():
            return BatchSummaryOutcome(
                entry_id=item.entry_id,
                title=item.title,
                ok=False,
                skipped=True,
                error="文章正文为空",
            )
        try:
            result = self._agent.run(item.request)
        except ProviderError as exc:
            return BatchSummaryOutcome(
                entry_id=item.entry_id,
                title=item.title,
                ok=False,
                error=str(exc),
            )
        except SummaryAgentError as exc:
            return BatchSummaryOutcome(
                entry_id=item.entry_id,
                title=item.title,
                ok=False,
                error=str(exc),
            )
        except Exception as exc:
            return BatchSummaryOutcome(
                entry_id=item.entry_id,
                title=item.title,
                ok=False,
                error=f"Unexpected: {exc}",
            )

        if not result.text.strip():
            return BatchSummaryOutcome(
                entry_id=item.entry_id,
                title=item.title,
                ok=False,
                error="Provider 返回空响应",
            )
        return BatchSummaryOutcome(
            entry_id=item.entry_id,
            title=item.title,
            ok=True,
            text=result.text,
            model_id=result.model_id,
            truncated=result.truncated,
        )
