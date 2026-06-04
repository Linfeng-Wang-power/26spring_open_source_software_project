"""OpenAI-compatible chat-completions provider over httpx.

Supports any base URL that exposes `/v1/chat/completions` with OpenAI semantics
(OpenAI, DeepSeek, Moonshot, Together, Ollama-compat, etc.).

Streaming uses Server-Sent Events: lines like `data: {...}` followed by a
terminal `data: [DONE]`.
"""

from __future__ import annotations

import json
from typing import Iterable, Iterator

import httpx

from agent.provider.llm_provider import (
    ChatMessage,
    LLMProvider,
    ProviderAuthError,
    ProviderConfig,
    ProviderHTTPError,
    ProviderTimeoutError,
)


class OpenAICompatibleProvider(LLMProvider):
    """Calls an OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._owned_client = client is None
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    @property
    def model(self) -> str:
        return self._config.model

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> "OpenAICompatibleProvider":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- Public API ----------------------------------------------------------

    def complete(self, messages: Iterable[ChatMessage]) -> str:
        url = self._endpoint()
        payload = self._payload(messages, stream=False)
        try:
            response = self._client.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc

        self._raise_for_status(response)
        data = response.json()
        return self._extract_text(data)

    def stream(self, messages: Iterable[ChatMessage]) -> Iterator[str]:
        url = self._endpoint()
        payload = self._payload(messages, stream=True)
        try:
            with self._client.stream(
                "POST",
                url,
                json=payload,
                headers=self._headers(),
                timeout=self._config.timeout_seconds,
            ) as response:
                self._raise_for_status(response)
                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str or data_str == "[DONE]":
                        if data_str == "[DONE]":
                            return
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = self._extract_delta(chunk)
                    if delta:
                        yield delta
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc

    # -- Internals -----------------------------------------------------------

    def _endpoint(self) -> str:
        base = self._config.base_url.rstrip("/")
        # Allow base_url that already includes /v1 or the full path.
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        for k, v in self._config.extra_headers.items():
            headers[k] = v
        return headers

    def _payload(
        self,
        messages: Iterable[ChatMessage],
        *,
        stream: bool,
    ) -> dict:
        return {
            "model": self._config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        try:
            body = response.text
        except Exception:
            body = ""
        if status in (401, 403):
            raise ProviderAuthError(f"Auth failed ({status})")
        raise ProviderHTTPError(status, body[:500])

    @staticmethod
    def _extract_text(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""

    @staticmethod
    def _extract_delta(chunk: dict) -> str:
        choices = chunk.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""
