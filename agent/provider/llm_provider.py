"""LLM provider boundary.

All summary/translation agents should depend on the abstract `LLMProvider`
protocol below, not on any specific HTTP client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Protocol


class ProviderError(Exception):
    """Base class for all provider errors."""


class ProviderTimeoutError(ProviderError):
    """Raised when an upstream call times out."""


class ProviderAuthError(ProviderError):
    """Raised on 401/403 from the upstream API."""


class ProviderHTTPError(ProviderError):
    """Raised on other non-2xx responses."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime config for an OpenAI-compatible provider.

    `api_key` is resolved at call time (keyring or env). It is never logged
    and never written to SQLite.
    """

    base_url: str
    model: str
    api_key: str = field(repr=False, default="")
    timeout_seconds: float = 60.0
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    """One chat-completions message."""

    role: str
    content: str


class LLMProvider(Protocol):
    """Provider-neutral chat-completions surface."""

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        """Return the full assistant text in one call."""
        ...

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        """Yield assistant text deltas as they arrive."""
        ...
