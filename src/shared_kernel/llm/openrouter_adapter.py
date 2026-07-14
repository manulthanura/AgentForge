"""OpenRouter adapter for the LLMProvider port.

OpenRouter exposes an OpenAI-compatible Chat Completions API, so this reuses
LangChain's ``langchain-openai`` ``ChatOpenAI`` pointed at OpenRouter's base
URL instead of adding a separate client. Model names are OpenRouter slugs
(e.g. "openai/gpt-4o", "anthropic/claude-sonnet-4.5") since OpenRouter routes
to many upstream providers behind one key.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMProvider, LLMResponse, Message


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    default_model = "openai/gpt-4o"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        # OpenRouter asks for these attribution headers on every request;
        # both are optional but recommended, so omit blank ones rather than
        # sending empty strings.
        headers = {}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name
        self._chat_model = ChatOpenAI(
            model=self.model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers=headers or None,
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
        model = self._chat_model.bind(max_tokens=max_tokens)
        if json_mode:
            model = model.bind(response_format={"type": "json_object"})
        try:
            response = model.invoke(lc_messages)
        except Exception as exc:
            # Covers OpenRouter's HTTP-200-with-null-choices-and-`error`
            # quirk (common on free-tier models) via the shared ValueError
            # mapping in raise_as_llm_error.
            raise_as_llm_error("OpenRouter", exc)

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model_name", self.model),
            stop_reason=response.response_metadata.get("finish_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )
