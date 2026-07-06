"""Each adapter maps the shared port onto its SDK correctly.

SDK clients are stubbed at the adapter boundary — no network traffic.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from shared_kernel.config.settings import Settings
from shared_kernel.llm import LLMError
from shared_kernel.llm.anthropic_adapter import AnthropicProvider
from shared_kernel.llm.ollama_adapter import OllamaProvider
from shared_kernel.llm.openai_adapter import OpenAIProvider

MESSAGES = [{"role": "user", "content": "hello"}]


# --- Anthropic -----------------------------------------------------------


class _StubAnthropicMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _anthropic_response(text="hi there"):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        model="claude-opus-4-8",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=12, output_tokens=7),
    )


def _make_anthropic(fake_keys) -> tuple[AnthropicProvider, _StubAnthropicMessages]:
    provider = AnthropicProvider(Settings())
    stub = _StubAnthropicMessages(_anthropic_response())
    provider._client = SimpleNamespace(messages=stub)
    return provider, stub


def test_anthropic_request_mapping(fake_keys):
    provider, stub = _make_anthropic(fake_keys)
    result = provider.complete(MESSAGES, system="be brief", max_tokens=1234)
    assert stub.kwargs["model"] == "claude-opus-4-8"
    assert stub.kwargs["system"] == "be brief"
    assert stub.kwargs["max_tokens"] == 1234
    assert stub.kwargs["messages"] == MESSAGES
    assert stub.kwargs["thinking"] == {"type": "adaptive"}
    # Thinking blocks are skipped; only text blocks are returned.
    assert result.text == "hi there"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 12
    assert result.output_tokens == 7


def test_anthropic_refusal_raises(fake_keys):
    provider, stub = _make_anthropic(fake_keys)
    stub.response = SimpleNamespace(
        content=[],
        model="claude-opus-4-8",
        stop_reason="refusal",
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
    )
    with pytest.raises(LLMError, match="refusal"):
        provider.complete(MESSAGES)


# --- OpenAI --------------------------------------------------------------


class _StubOpenAICompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _openai_response(text="hi from gpt"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text), finish_reason="stop"
            )
        ],
        model="gpt-4o",
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=9),
    )


def test_openai_request_mapping(fake_keys):
    provider = OpenAIProvider(Settings())
    stub = _StubOpenAICompletions(_openai_response())
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=stub)
    )
    result = provider.complete(
        MESSAGES, system="be brief", max_tokens=777, json_mode=True
    )
    assert stub.kwargs["model"] == "gpt-4o"
    assert stub.kwargs["max_completion_tokens"] == 777
    assert stub.kwargs["response_format"] == {"type": "json_object"}
    # System prompt becomes the leading system message.
    assert stub.kwargs["messages"][0] == {"role": "system", "content": "be brief"}
    assert stub.kwargs["messages"][1:] == MESSAGES
    assert result.text == "hi from gpt"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 20
    assert result.output_tokens == 9


# --- Ollama --------------------------------------------------------------


class _StubHttpxClient:
    def __init__(self, payload):
        self.payload = payload
        self.path = None
        self.json_body = None

    def post(self, path, json=None):
        self.path = path
        self.json_body = json
        request = httpx.Request("POST", "http://localhost:11434" + path)
        return httpx.Response(200, json=self.payload, request=request)


def test_ollama_request_mapping(fake_keys):
    provider = OllamaProvider(Settings())
    stub = _StubHttpxClient(
        {
            "model": "llama3.1",
            "message": {"role": "assistant", "content": "hi from llama"},
            "done_reason": "stop",
            "prompt_eval_count": 15,
            "eval_count": 6,
        }
    )
    provider._client = stub
    result = provider.complete(
        MESSAGES, system="be brief", max_tokens=512, json_mode=True
    )
    assert stub.path == "/api/chat"
    assert stub.json_body["model"] == "llama3.1"
    assert stub.json_body["stream"] is False
    assert stub.json_body["format"] == "json"
    assert stub.json_body["options"] == {"num_predict": 512}
    assert stub.json_body["messages"][0] == {"role": "system", "content": "be brief"}
    assert result.text == "hi from llama"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 15
    assert result.output_tokens == 6


def test_ollama_http_error_becomes_llm_error(fake_keys):
    provider = OllamaProvider(Settings())

    class _Boom:
        def post(self, path, json=None):
            raise httpx.ConnectError("connection refused")

    provider._client = _Boom()
    # Connection failures are transient -> retryable LLMUnavailableError
    # (still an LLMError for callers that don't care about the distinction).
    with pytest.raises(LLMError, match="Ollama unreachable"):
        provider.complete(MESSAGES)
