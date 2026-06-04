"""Summary agent: orchestrates prompt rendering, provider call, and storage.

This module is GUI-free. It receives a provider and a store, builds the prompt
from the YAML template, calls the provider (streaming), and persists on success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

from mercury.agent.provider.llm_provider import ChatMessage, LLMProvider, ProviderError
from mercury.agent.prompts.template_renderer import (
    PromptTemplate,
    RenderedPrompt,
    load_template,
    render_template,
)

DETAIL_LEVELS = ("short", "default", "detailed")

DEFAULT_MAX_CONTENT_CHARS = 12000
TRUNCATION_NOTICE = "\n\n[…内容因长度限制已裁剪…]\n\n"


class SummaryAgentError(Exception):
    """Raised when the summary flow fails in a non-provider way."""


@dataclass(frozen=True)
class SummaryRequest:
    """Everything the agent needs to run one summary."""

    entry_id: str
    title: str
    content: str
    target_language: str = "zh-CN"
    detail_level: str = "default"
    max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS


@dataclass(frozen=True)
class SummaryResult:
    """Returned on a successful run."""

    entry_id: str
    text: str
    model_id: str
    template_fingerprint: str
    truncated: bool = False


def truncate_content(text: str, max_chars: int) -> tuple[str, bool]:
    """Trim *text* to roughly *max_chars*, preserving head and tail.

    Returns ``(possibly_trimmed, truncated_flag)``. When ``max_chars`` is
    non-positive, no trimming happens. When the text already fits, it is
    returned unchanged.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    # Keep ~60% of the budget at the head, ~40% at the tail. Headlines and
    # the lead paragraph carry the most signal; the closing paragraph often
    # has a conclusion. We splice the truncation notice between them so the
    # model knows what happened.
    notice_len = len(TRUNCATION_NOTICE)
    body_budget = max(0, max_chars - notice_len)
    head_len = int(body_budget * 0.6)
    tail_len = body_budget - head_len
    head = text[:head_len].rstrip()
    tail = text[-tail_len:].lstrip() if tail_len > 0 else ""
    return f"{head}{TRUNCATION_NOTICE}{tail}", True


class SummaryAgent:
    """Stateless summary executor.

    Typical usage::

        agent = SummaryAgent(provider=provider)
        result = agent.run(request)
        store.save_result(result.entry_id, result.text, result.model_id)

    For streaming, use ``stream()`` which yields token deltas.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        template: PromptTemplate | None = None,
    ) -> None:
        self._provider = provider
        self._template = template or load_template("summary.default")

    @property
    def template(self) -> PromptTemplate:
        return self._template

    def run(self, request: SummaryRequest) -> SummaryResult:
        """Non-streaming: call provider.complete(), return full result."""
        rendered, truncated = self._render(request)
        messages = [ChatMessage(role=m.role, content=m.content) for m in rendered.messages]
        try:
            text = self._provider.complete(messages)
        except ProviderError:
            raise
        except Exception as exc:
            raise SummaryAgentError(f"Unexpected error: {exc}") from exc

        return SummaryResult(
            entry_id=request.entry_id,
            text=text.strip(),
            model_id=self._model_tag(rendered),
            template_fingerprint=rendered.template_fingerprint,
            truncated=truncated,
        )

    def stream(
        self,
        request: SummaryRequest,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> SummaryResult:
        """Streaming: yield token deltas via provider.stream().

        If *on_token* is provided, each delta is passed to the callback (useful
        for Qt worker signal throttling). Returns the assembled result.
        """
        rendered, truncated = self._render(request)
        messages = [ChatMessage(role=m.role, content=m.content) for m in rendered.messages]

        accumulated: list[str] = []
        try:
            for delta in self._provider.stream(messages):
                accumulated.append(delta)
                if on_token:
                    on_token(delta)
        except ProviderError:
            raise
        except Exception as exc:
            raise SummaryAgentError(f"Stream error: {exc}") from exc

        full_text = "".join(accumulated).strip()
        if not full_text:
            raise SummaryAgentError("Provider returned empty response")

        return SummaryResult(
            entry_id=request.entry_id,
            text=full_text,
            model_id=self._model_tag(rendered),
            template_fingerprint=rendered.template_fingerprint,
            truncated=truncated,
        )

    def stream_iter(self, request: SummaryRequest) -> Iterator[str]:
        """Low-level iterator variant for callers who want raw deltas."""
        rendered, _ = self._render(request)
        messages = [ChatMessage(role=m.role, content=m.content) for m in rendered.messages]
        yield from self._provider.stream(messages)

    # -- Internal -------------------------------------------------------------

    def _render(self, request: SummaryRequest) -> tuple[RenderedPrompt, bool]:
        if request.detail_level not in DETAIL_LEVELS:
            raise SummaryAgentError(
                f"Invalid detail_level: {request.detail_level!r}; "
                f"expected one of {DETAIL_LEVELS}"
            )
        content, truncated = truncate_content(request.content, request.max_content_chars)
        variables = {
            "target_language": request.target_language,
            "detail_level": request.detail_level,
            "title": request.title,
            "content": content,
        }
        return render_template(self._template, variables), truncated

    def _model_tag(self, rendered: RenderedPrompt) -> str:
        model = getattr(self._provider, "model", "unknown")
        return f"{model}@{rendered.template_fingerprint}"
