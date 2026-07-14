"""Shared message/usage/error-mapping helpers used by all LangChain-backed
LLM adapters."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from shared_kernel.llm import LLMError, LLMRateLimitError, LLMUnavailableError
from shared_kernel.llm.langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)

MESSAGES = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]


def test_to_langchain_messages_maps_roles_and_prepends_system():
    lc_messages = to_langchain_messages(MESSAGES, system="be brief")
    assert [type(m).__name__ for m in lc_messages] == [
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert lc_messages[0].content == "be brief"
    assert lc_messages[1].content == "hello"
    assert lc_messages[2].content == "hi"


def test_to_langchain_messages_without_system():
    lc_messages = to_langchain_messages(MESSAGES, system=None)
    assert len(lc_messages) == 2


def test_token_usage_extracts_input_output_tokens():
    response = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 4})
    assert token_usage(response) == (10, 4)


def test_token_usage_missing_returns_none_pair():
    response = SimpleNamespace(usage_metadata=None)
    assert token_usage(response) == (None, None)


def test_status_code_429_is_rate_limit_error():
    class FakeError(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "3"})

    with pytest.raises(LLMRateLimitError) as exc_info:
        raise_as_llm_error("Gemini", FakeError("boom"))
    assert exc_info.value.retry_after == 3.0


def test_status_code_5xx_is_unavailable_error():
    class FakeError(Exception):
        status_code = 503

    with pytest.raises(LLMUnavailableError):
        raise_as_llm_error("Hugging Face", FakeError("boom"))


def test_connection_error_is_unavailable_error():
    with pytest.raises(LLMUnavailableError):
        raise_as_llm_error("Azure OpenAI", ConnectionError("refused"))


def test_other_errors_become_generic_llm_error():
    with pytest.raises(LLMError):
        raise_as_llm_error("Gemini", ValueError("bad request"))


def test_httpx_transport_error_is_unavailable_error():
    # Ollama's streaming path can leak a raw httpx.TransportError unwrapped
    # (its non-streaming path normalizes these to a builtin ConnectionError).
    with pytest.raises(LLMUnavailableError):
        raise_as_llm_error("Ollama", httpx.ConnectError("refused"))


def test_openai_style_null_choices_value_error_is_unavailable():
    # langchain-openai raises ValueError(error_dict) for OpenAI-compatible
    # APIs (e.g. OpenRouter) that return HTTP 200 with null `choices` and an
    # embedded `error` instead of an HTTP error status.
    payload = {"message": "upstream provider timed out"}
    with pytest.raises(LLMUnavailableError, match="upstream provider timed out"):
        raise_as_llm_error("OpenRouter", ValueError(payload))


def test_openai_style_null_choices_with_429_code_is_rate_limit_error():
    payload = {"code": 429, "message": "rate limited upstream"}
    with pytest.raises(LLMRateLimitError, match="rate limited upstream"):
        raise_as_llm_error("OpenRouter", ValueError(payload))


def test_response_text_handles_string_content():
    response = SimpleNamespace(text="hi there")
    assert response_text(response) == "hi there"


def test_response_text_handles_none():
    response = SimpleNamespace(text=None)
    assert response_text(response) == ""
