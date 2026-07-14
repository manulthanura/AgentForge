"""Anthropic (Claude) adapter for the LLMProvider port.

Built on LangChain's ``langchain-anthropic`` integration (``ChatAnthropic``)
rather than a raw ``anthropic`` SDK client.
"""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMError, LLMProvider, LLMResponse, Message


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-4-8"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._chat_model = ChatAnthropic(
            model=self.model,
            api_key=settings.anthropic_api_key,
            thinking={"type": "adaptive"},
        )

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        # json_mode is prompt-level for Anthropic; complete_json adds the
        # instruction and parses robustly.
        lc_messages = to_langchain_messages(messages, system)
        try:
            response = self._chat_model.bind(max_tokens=max_tokens).invoke(
                lc_messages
            )
        except Exception as exc:
            raise_as_llm_error("Anthropic", exc)

        if response.response_metadata.get("stop_reason") == "refusal":
            raise LLMError("Anthropic declined the request (stop_reason=refusal)")

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model", self.model),
            stop_reason=response.response_metadata.get("stop_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )
