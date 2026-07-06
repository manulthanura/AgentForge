"""Adapters classify provider failures into transient vs. permanent errors.

Simulated 503/429 responses at the SDK boundary must surface as
LLMUnavailableError / LLMRateLimitError so the retry layer can react.
"""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import openai
import pytest

from shared_kernel.config.settings import Settings
from shared_kernel.llm import LLMError, LLMRateLimitError, LLMUnavailableError
from shared_kernel.llm.anthropic_adapter import AnthropicProvider
from shared_kernel.llm.ollama_adapter import OllamaProvider
from shared_kernel.llm.openai_adapter import OpenAIProvider

MESSAGES = [{"role": "user", "content": "hi"}]


def _http_response(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.example.com/v1"),
    )


class _Raiser:
    def __init__(self, exc):
        self.exc = exc

    def create(self, **kwargs):
        raise self.exc


# --- Anthropic ----------------------------------------------------------------


def _anthropic_with(exc) -> AnthropicProvider:
    provider = AnthropicProvider(Settings())
    provider._client = SimpleNamespace(messages=_Raiser(exc))
    return provider


def test_anthropic_503_is_transient(fake_keys):
    exc = anthropic.APIStatusError(
        "overloaded", response=_http_response(503), body=None
    )
    with pytest.raises(LLMUnavailableError):
        _anthropic_with(exc).complete(MESSAGES)


def test_anthropic_429_carries_retry_after(fake_keys):
    exc = anthropic.APIStatusError(
        "rate limited",
        response=_http_response(429, headers={"retry-after": "12"}),
        body=None,
    )
    with pytest.raises(LLMRateLimitError) as excinfo:
        _anthropic_with(exc).complete(MESSAGES)
    assert excinfo.value.retry_after == 12.0


def test_anthropic_400_is_permanent(fake_keys):
    exc = anthropic.APIStatusError(
        "bad request", response=_http_response(400), body=None
    )
    with pytest.raises(LLMError) as excinfo:
        _anthropic_with(exc).complete(MESSAGES)
    assert not isinstance(excinfo.value, LLMUnavailableError)


# --- OpenAI --------------------------------------------------------------------


def _openai_with(exc) -> OpenAIProvider:
    provider = OpenAIProvider(Settings())
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=_Raiser(exc))
    )
    return provider


def test_openai_503_is_transient(fake_keys):
    exc = openai.APIStatusError(
        "unavailable", response=_http_response(503), body=None
    )
    with pytest.raises(LLMUnavailableError):
        _openai_with(exc).complete(MESSAGES)


def test_openai_429_carries_retry_after(fake_keys):
    exc = openai.APIStatusError(
        "rate limited",
        response=_http_response(429, headers={"retry-after": "5"}),
        body=None,
    )
    with pytest.raises(LLMRateLimitError) as excinfo:
        _openai_with(exc).complete(MESSAGES)
    assert excinfo.value.retry_after == 5.0


# --- Ollama --------------------------------------------------------------------


class _OllamaStub:
    def __init__(self, status: int):
        self.status = status

    def post(self, path, json=None):
        return httpx.Response(
            self.status,
            request=httpx.Request("POST", "http://localhost:11434" + path),
        )


def test_ollama_503_is_transient(fake_keys):
    provider = OllamaProvider(Settings())
    provider._client = _OllamaStub(503)
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_ollama_connection_error_is_transient(fake_keys):
    provider = OllamaProvider(Settings())

    class _Down:
        def post(self, path, json=None):
            raise httpx.ConnectError("refused")

    provider._client = _Down()
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_ollama_404_is_permanent(fake_keys):
    provider = OllamaProvider(Settings())
    provider._client = _OllamaStub(404)
    with pytest.raises(LLMError) as excinfo:
        provider.complete(MESSAGES)
    assert not isinstance(excinfo.value, LLMUnavailableError)
