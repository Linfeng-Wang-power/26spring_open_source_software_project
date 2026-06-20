"""Translation agent built on the provider-neutral LLM boundary."""

from __future__ import annotations

from dataclasses import dataclass

from mercury.agent.provider.llm_provider import ChatMessage, LLMProvider, ProviderError
from mercury.agent.prompts.template_renderer import (
    PromptTemplate,
    RenderedPrompt,
    load_template,
    render_template,
)
from mercury.agent.translation.segmenter import SourceSegment, segment_markdown


class TranslationAgentError(Exception):
    """Raised when translation fails outside provider transport errors."""


@dataclass(frozen=True)
class TranslationRequest:
    """Input for translating one article."""

    entry_id: str
    title: str
    content: str
    target_language: str = "zh-CN"

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise TranslationAgentError("entry_id must not be empty")
        if not self.content or not self.content.strip():
            raise TranslationAgentError("content must not be empty")
        if not self.target_language or not self.target_language.strip():
            raise TranslationAgentError("target_language must not be empty")


@dataclass(frozen=True)
class TranslationSegment:
    """One translated segment."""

    source_text: str
    trans_text: str
    source_hash: str
    position: int


@dataclass(frozen=True)
class TranslationResult:
    """Result for one article translation run."""

    entry_id: str
    target_language: str
    segments: tuple[TranslationSegment, ...]
    model_id: str
    template_fingerprint: str


class TranslationAgent:
    """Serial paragraph-level translator."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        template: PromptTemplate | None = None,
    ) -> None:
        self._provider = provider
        self._template = template or load_template("translation.default")

    @property
    def template(self) -> PromptTemplate:
        return self._template

    @property
    def provider_model(self) -> str:
        return getattr(self._provider, "model")

    def build_model_id(self) -> str:
        return f"{self.provider_model}@{self._template.fingerprint}"

    def run(self, request: TranslationRequest) -> TranslationResult:
        """Translate all extracted segments using non-streaming calls."""
        source_segments = segment_markdown(request.content)
        if not source_segments:
            raise TranslationAgentError("No translatable segments found")

        translated: list[TranslationSegment] = []
        fingerprint = self._template.fingerprint
        for source in source_segments:
            rendered = self._render(request, source)
            messages = [
                ChatMessage(role=m.role, content=m.content)
                for m in rendered.messages
            ]
            try:
                text = self._provider.complete(messages)
            except ProviderError:
                raise
            except Exception as exc:
                raise TranslationAgentError(f"Unexpected error: {exc}") from exc

            trans_text = (text or "").strip()
            if not trans_text:
                raise TranslationAgentError(
                    f"Provider returned empty response for segment {source.position}"
                )
            translated.append(
                TranslationSegment(
                    source_text=source.source_text,
                    trans_text=trans_text,
                    source_hash=source.source_hash,
                    position=source.position,
                )
            )
            fingerprint = rendered.template_fingerprint

        return TranslationResult(
            entry_id=request.entry_id,
            target_language=request.target_language,
            segments=tuple(translated),
            model_id=self.build_model_id(),
            template_fingerprint=fingerprint,
        )

    def _render(
        self, request: TranslationRequest, source: SourceSegment
    ) -> RenderedPrompt:
        variables = {
            "target_language": request.target_language,
            "title": request.title,
            "segment": source.source_text,
            "position": str(source.position),
        }
        return render_template(self._template, variables)
