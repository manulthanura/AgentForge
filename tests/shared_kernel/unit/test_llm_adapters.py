"""Each adapter maps the shared port onto its LangChain chat model correctly.

All seven adapters (Anthropic, OpenAI, Ollama, OpenRouter, Azure OpenAI,
Gemini, Hugging Face) wrap a LangChain ``BaseChatModel`` rather than a raw
vendor SDK, so a stub only needs to mimic `.bind(**kwargs).invoke(messages)`
and return a real ``AIMessage`` (content / response_metadata /
usage_metadata) — no network traffic anywhere.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from shared_kernel.config.settings import Settings
from shared_kernel.llm import LLMError, LLMUnavailableError
from shared_kernel.llm.anthropic_adapter import AnthropicProvider
from shared_kernel.llm.azure_openai_adapter import AzureOpenAIProvider
from shared_kernel.llm.gemini_adapter import GeminiProvider
from shared_kernel.llm.huggingface_adapter import HuggingFaceProvider
from shared_kernel.llm.ollama_adapter import OllamaProvider
from shared_kernel.llm.openai_adapter import OpenAIProvider
from shared_kernel.llm.openrouter_adapter import OpenRouterProvider

MESSAGES = [{"role": "user", "content": "hello"}]


class _StubChatModel:
    def __init__(self, response):
        self.response = response
        self.bind_kwargs: dict = {}
        self.invoked_messages = None

    def bind(self, **kwargs):
        self.bind_kwargs.update(kwargs)
        return self

    def invoke(self, messages):
        self.invoked_messages = messages
        return self.response


class _RaisingChatModel:
    def __init__(self, exc):
        self.exc = exc

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        raise self.exc


def _ai_message(text="hi there", input_tokens=18, output_tokens=5, content=None, **metadata):
    return AIMessage(
        content=content if content is not None else text,
        response_metadata=metadata,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


# --- Anthropic -------------------------------------------------------------


def test_anthropic_configures_adaptive_thinking(fake_keys):
    # `thinking` is set once at ChatAnthropic construction, not per-call, so
    # this is verified directly on the real (cheap, network-free) client
    # rather than through a stub.
    provider = AnthropicProvider(Settings())
    assert provider._chat_model.thinking == {"type": "adaptive"}


def test_anthropic_request_mapping(fake_keys):
    provider = AnthropicProvider(Settings())
    stub = _StubChatModel(
        _ai_message(
            content=[
                {"type": "thinking", "thinking": ""},
                {"type": "text", "text": "hi there"},
            ],
            model="claude-opus-4-8",
            stop_reason="end_turn",
        )
    )
    provider._chat_model = stub
    result = provider.complete(MESSAGES, system="be brief", max_tokens=1234)
    assert stub.bind_kwargs == {"max_tokens": 1234}
    assert stub.invoked_messages[0].content == "be brief"
    # Thinking blocks are skipped; only text blocks are returned.
    assert result.text == "hi there"
    assert result.model == "claude-opus-4-8"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_anthropic_refusal_raises(fake_keys):
    provider = AnthropicProvider(Settings())
    provider._chat_model = _StubChatModel(
        _ai_message(text="", model="claude-opus-4-8", stop_reason="refusal")
    )
    with pytest.raises(LLMError, match="refusal"):
        provider.complete(MESSAGES)


def test_anthropic_5xx_becomes_llm_unavailable_error(fake_keys):
    provider = AnthropicProvider(Settings())

    class FakeError(Exception):
        status_code = 529  # Anthropic's "overloaded" status

    provider._chat_model = _RaisingChatModel(FakeError("overloaded"))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


# --- OpenAI ------------------------------------------------------------


def test_openai_request_mapping(fake_keys):
    provider = OpenAIProvider(Settings())
    stub = _StubChatModel(
        _ai_message(text="hi from gpt", model_name="gpt-4o", finish_reason="stop")
    )
    provider._chat_model = stub
    result = provider.complete(
        MESSAGES, system="be brief", max_tokens=777, json_mode=True
    )
    assert stub.bind_kwargs["max_tokens"] == 777
    assert stub.bind_kwargs["response_format"] == {"type": "json_object"}
    assert stub.invoked_messages[0].content == "be brief"
    assert result.text == "hi from gpt"
    assert result.model == "gpt-4o"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_openai_5xx_becomes_llm_unavailable_error(fake_keys):
    provider = OpenAIProvider(Settings())

    class FakeError(Exception):
        status_code = 503

    provider._chat_model = _RaisingChatModel(FakeError("unavailable"))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


# --- Ollama --------------------------------------------------------------


def test_ollama_request_mapping(fake_keys):
    provider = OllamaProvider(Settings())
    stub = _StubChatModel(
        _ai_message(text="hi from llama", model="llama3.1", done_reason="stop")
    )
    provider._chat_model = stub
    result = provider.complete(
        MESSAGES, system="be brief", max_tokens=512, json_mode=True
    )
    assert stub.bind_kwargs == {"num_predict": 512, "format": "json"}
    assert stub.invoked_messages[0].content == "be brief"
    assert result.text == "hi from llama"
    assert result.model == "llama3.1"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_ollama_connection_error_becomes_llm_unavailable_error(fake_keys):
    provider = OllamaProvider(Settings())
    provider._chat_model = _RaisingChatModel(ConnectionError("connection refused"))
    with pytest.raises(LLMUnavailableError, match="Ollama unreachable"):
        provider.complete(MESSAGES)


# --- OpenRouter --------------------------------------------------------


def test_openrouter_uses_openai_compatible_base_url(fake_keys):
    provider = OpenRouterProvider(Settings())
    assert str(provider._chat_model.openai_api_base) == "https://openrouter.ai/api/v1"
    assert provider.model == "openai/gpt-4o"


def test_openrouter_attribution_headers_are_optional(fake_keys):
    # No OPENROUTER_SITE_URL / OPENROUTER_APP_NAME set -> no extra headers.
    provider = OpenRouterProvider(Settings())
    headers = provider._chat_model.default_headers or {}
    assert "HTTP-Referer" not in headers
    assert "X-Title" not in headers


def test_openrouter_attribution_headers_when_configured(monkeypatch, fake_keys):
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "AgentForge")
    provider = OpenRouterProvider(Settings())
    headers = provider._chat_model.default_headers
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "AgentForge"


def test_openrouter_request_mapping(fake_keys):
    provider = OpenRouterProvider(Settings())
    stub = _StubChatModel(
        _ai_message(
            text="hi from openrouter", model_name="openai/gpt-4o", finish_reason="stop"
        )
    )
    provider._chat_model = stub
    result = provider.complete(
        MESSAGES, system="be brief", max_tokens=555, json_mode=True
    )
    assert stub.bind_kwargs["max_tokens"] == 555
    assert stub.bind_kwargs["response_format"] == {"type": "json_object"}
    assert result.text == "hi from openrouter"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_openrouter_null_choices_becomes_llm_unavailable_error(fake_keys):
    # langchain-openai raises ValueError(error_dict) when an OpenAI-compatible
    # API (like OpenRouter's free-tier models) returns HTTP 200 with a null
    # `choices` and an embedded `error`, instead of an HTTP error status.
    provider = OpenRouterProvider(Settings())
    provider._chat_model = _RaisingChatModel(
        ValueError({"message": "upstream provider timed out"})
    )
    with pytest.raises(LLMUnavailableError, match="upstream provider timed out"):
        provider.complete(MESSAGES)


# --- Azure OpenAI, Gemini, Hugging Face -----------------------------------


def test_azure_openai_request_mapping(fake_keys):
    provider = AzureOpenAIProvider(Settings())
    stub = _StubChatModel(
        _ai_message(text="hi from azure", model_name="gpt-4o", finish_reason="stop")
    )
    provider._chat_model = stub
    result = provider.complete(MESSAGES, system="be brief", max_tokens=555)
    assert stub.bind_kwargs == {"max_tokens": 555}
    assert stub.invoked_messages[0].content == "be brief"
    assert result.text == "hi from azure"
    assert result.model == "gpt-4o"
    assert result.stop_reason == "stop"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_azure_openai_json_mode_binds_response_format(fake_keys):
    provider = AzureOpenAIProvider(Settings())
    stub = _StubChatModel(_ai_message())
    provider._chat_model = stub
    provider.complete(MESSAGES, json_mode=True)
    assert stub.bind_kwargs["response_format"] == {"type": "json_object"}


def test_azure_openai_5xx_becomes_llm_unavailable_error(fake_keys):
    provider = AzureOpenAIProvider(Settings())

    class FakeError(Exception):
        status_code = 503

    provider._chat_model = _RaisingChatModel(FakeError("overloaded"))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_gemini_request_mapping(fake_keys):
    provider = GeminiProvider(Settings())
    stub = _StubChatModel(
        _ai_message(
            text="hi from gemini", model_name="gemini-2.5-flash", finish_reason="stop"
        )
    )
    provider._chat_model = stub
    result = provider.complete(MESSAGES, system="be brief", max_tokens=777)
    assert stub.bind_kwargs == {"max_output_tokens": 777}
    assert result.text == "hi from gemini"
    assert result.model == "gemini-2.5-flash"
    assert result.input_tokens == 18
    assert result.output_tokens == 5


def test_gemini_5xx_becomes_llm_unavailable_error(fake_keys):
    provider = GeminiProvider(Settings())

    class FakeError(Exception):
        code = 503

    provider._chat_model = _RaisingChatModel(FakeError("unavailable"))
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)


def test_huggingface_stays_lazy_until_first_use(fake_keys):
    # Constructing the provider must not build the real HuggingFaceEndpoint /
    # ChatHuggingFace client (tokenizer/chat-template resolution can touch
    # the network) — it should only happen on first `complete()` call.
    provider = HuggingFaceProvider(Settings())
    assert provider._chat_model is None


def test_huggingface_request_mapping(fake_keys):
    provider = HuggingFaceProvider(Settings())
    stub = _StubChatModel(
        _ai_message(text="hi from an open model", model="x", finish_reason="stop")
    )
    provider._chat_model = stub  # pre-populate to skip real construction
    result = provider.complete(MESSAGES, max_tokens=333)
    assert stub.bind_kwargs == {"max_tokens": 333}
    assert result.text == "hi from an open model"


def test_huggingface_5xx_becomes_llm_unavailable_error(fake_keys):
    provider = HuggingFaceProvider(Settings())

    class FakeError(Exception):
        pass

    err = FakeError("service unavailable")
    err.response = type("R", (), {"status_code": 503, "headers": {}})()
    provider._chat_model = _RaisingChatModel(err)
    with pytest.raises(LLMUnavailableError):
        provider.complete(MESSAGES)
