"""Ollama (local LLM) adapter for the LLMProvider port.

Built on LangChain's ``langchain-ollama`` integration (``ChatOllama``)
rather than talking to the Ollama HTTP API directly.
"""

from __future__ import annotations

from langchain_ollama import ChatOllama

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMProvider, LLMResponse, Message


class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "llama3.1"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._chat_model = ChatOllama(
            model=self.model,
            base_url=settings.ollama_base_url,
            # Don't probe the server for model metadata at construction —
            # keep this adapter cheap and network-free until first use.
            validate_model_on_init=False,
        )

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        lc_messages = to_langchain_messages(messages, system)
        model = self._chat_model.bind(num_predict=max_tokens)
        if json_mode:
            model = model.bind(format="json")
        try:
            response = model.invoke(lc_messages)
        except Exception as exc:
            raise_as_llm_error("Ollama", exc)

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model", self.model),
            stop_reason=response.response_metadata.get("done_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )
