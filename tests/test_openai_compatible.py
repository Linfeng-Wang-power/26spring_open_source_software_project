"""Tests for OpenAICompatibleProvider, including SSE streaming.

All HTTP traffic is mocked with respx so tests never hit a real provider.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from mercury.agent.provider.llm_provider import (
    ChatMessage,
    ProviderAuthError,
    ProviderConfig,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from mercury.agent.provider.openai_compatible import OpenAICompatibleProvider


def _config(base_url: str = "https://api.example.com") -> ProviderConfig:
    return ProviderConfig(
        base_url=base_url,
        model="test-model",
        api_key="sk-test",
        timeout_seconds=5.0,
    )


@respx.mock
def test_complete_returns_assistant_text() -> None:
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "hi"}}
                ],
            },
        )
    )
    with OpenAICompatibleProvider(_config()) as p:
        text = p.complete([ChatMessage("user", "hello")])
    assert text == "hi"
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer sk-test"


@respx.mock
def test_endpoint_when_base_url_has_v1() -> None:
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )
    )
    cfg = ProviderConfig(
        base_url="https://api.example.com/v1",
        model="m",
        api_key="k",
    )
    with OpenAICompatibleProvider(cfg) as p:
        assert p.complete([ChatMessage("user", "x")]) == "ok"
    assert route.called


@respx.mock
def test_endpoint_when_base_url_is_full_path() -> None:
    route = respx.post("https://x.example.com/foo/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )
    )
    cfg = ProviderConfig(
        base_url="https://x.example.com/foo/chat/completions",
        model="m",
        api_key="k",
    )
    with OpenAICompatibleProvider(cfg) as p:
        assert p.complete([ChatMessage("user", "x")]) == "ok"
    assert route.called


@respx.mock
def test_auth_error_maps_to_provider_auth_error() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with OpenAICompatibleProvider(_config()) as p:
        with pytest.raises(ProviderAuthError):
            p.complete([ChatMessage("user", "x")])


@respx.mock
def test_http_error_maps_to_provider_http_error() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with OpenAICompatibleProvider(_config()) as p:
        with pytest.raises(ProviderHTTPError) as exc_info:
            p.complete([ChatMessage("user", "x")])
        assert exc_info.value.status_code == 500


@respx.mock
def test_timeout_maps_to_provider_timeout() -> None:
    respx.post("https://api.example.com/v1/chat/completions").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    with OpenAICompatibleProvider(_config()) as p:
        with pytest.raises(ProviderTimeoutError):
            p.complete([ChatMessage("user", "x")])


@respx.mock
def test_stream_yields_token_deltas() -> None:
    sse_body = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body,
        )
    )
    with OpenAICompatibleProvider(_config()) as p:
        chunks = list(p.stream([ChatMessage("user", "x")]))
    assert chunks == ["Hel", "lo", " world"]
    assert "".join(chunks) == "Hello world"


@respx.mock
def test_stream_skips_blank_and_unparseable_lines() -> None:
    sse_body = (
        b'\n'
        b'data: \n'
        b'data: not-json\n\n'
        b'data: {"choices":[{"delta":{"content":"X"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body,
        )
    )
    with OpenAICompatibleProvider(_config()) as p:
        chunks = list(p.stream([ChatMessage("user", "x")]))
    assert chunks == ["X"]


@respx.mock
def test_stream_does_not_log_api_key() -> None:
    """Sanity: api key only shows in Authorization header, not in payload."""
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=b'data: [DONE]\n\n',
        )
    )
    cfg = _config()
    with OpenAICompatibleProvider(cfg) as p:
        list(p.stream([ChatMessage("user", "secret prompt")]))
    last = respx.calls.last.request
    body = last.content.decode()
    assert "sk-test" not in body
