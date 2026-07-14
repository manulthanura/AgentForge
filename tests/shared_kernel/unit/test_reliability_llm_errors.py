"""Adapters classify provider failures into transient vs. permanent errors.

Simulated 503/429/connection failures at the chat-model boundary must
surface as LLMUnavailableError / LLMRateLimitError so the retry layer can
react. All adapters share the same LangChain-based error mapping
(shared_kernel/llm/langchain_support.py::raise_as_llm_error), so this
exercises it through each adapter's `complete()` rather than duplicating
SDK-specific exception construction per provider.
"""

from __future__ import annotations

import pytest

from shared_kernel.config.settings import Settings
from shared_kernel.llm import LLMError, LLMRateLimitError, LLMUnavailableError
from shared_kernel.llm.anthropic_adapter import AnthropicProvider
from shared_kernel.llm.ollama_adapter import OllamaProvider
from shared_kernel.llm.openai_adapter import OpenAIProvider

MESSAGES = [{"role": "user", "content": "hi"}]


class _RaisingChatModel:
    def __init__(self, exc):
        self.exc = exc

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        raise self.exc


def _with_status(status: int, retry_after: str | None = None) -> Exception:
    exc = Exception(f"boom ({status})")
    exc.status_code = status
    if retry_after is not None:
        exc.response = type(
            "R", (), {"headers": {"retry-after": retry_after}, "status_code": status}
        )()
    return exc


# --- Anthropic ------------------------------------------------------------


def test_anthropic_503_is_transient(fake_keys):
    provider = AnthropicProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(503))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_anthropic_429_carries_retry_after(fake_keys):
    provider = AnthropicProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(429, retry_after="12"))
    with pytest.raises(LLMRateLimitError) as excinfo:
        provider.complete(MESSAGES)
    assert excinfo.value.retry_after == 12.0


def test_anthropic_400_is_permanent(fake_keys):
    provider = AnthropicProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(400))
    with pytest.raises(LLMError) as excinfo:
        provider.complete(MESSAGES)
    assert not isinstance(excinfo.value, LLMUnavailableError)


# --- OpenAI -----------------------------------------------------------------


def test_openai_503_is_transient(fake_keys):
    provider = OpenAIProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(503))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_openai_429_carries_retry_after(fake_keys):
    provider = OpenAIProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(429, retry_after="5"))
    with pytest.raises(LLMRateLimitError) as excinfo:
        provider.complete(MESSAGES)
    assert excinfo.value.retry_after == 5.0


# --- Ollama ------------------------------------------------------------------


def test_ollama_503_is_transient(fake_keys):
    provider = OllamaProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(503))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_ollama_connection_error_is_transient(fake_keys):
    provider = OllamaProvider(Settings())
    provider._chat_model = _RaisingChatModel(ConnectionError("refused"))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_ollama_404_is_permanent(fake_keys):
    provider = OllamaProvider(Settings())
    provider._chat_model = _RaisingChatModel(_with_status(404))
    with pytest.raises(LLMError) as excinfo:
        provider.complete(MESSAGES)
    assert not isinstance(excinfo.value, LLMUnavailableError)
