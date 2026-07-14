"""Azure OpenAI adapter for the LLMProvider port.

Built on LangChain's ``langchain-openai`` integration (``AzureChatOpenAI``)
rather than a hand-rolled ``openai.AzureOpenAI`` client, so deployment/API
version handling and auth stay on LangChain's maintained wrapper.
"""

from __future__ import annotations

from langchain_openai import AzureChatOpenAI

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMProvider, LLMResponse, Message


class AzureOpenAIProvider(LLMProvider):
    name = "azure"
    default_model = "gpt-4o"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._chat_model = AzureChatOpenAI(
            model=self.model,
            azure_deployment=settings.azure_openai_deployment or self.model,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
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
            # Native JSON enforcement, same as the raw OpenAI/OpenRouter
            # adapters — Azure OpenAI shares the Chat Completions contract.
            model = model.bind(response_format={"type": "json_object"})
        try:
            response = model.invoke(lc_messages)
        except Exception as exc:
            raise_as_llm_error("Azure OpenAI", exc)

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model_name", self.model),
            stop_reason=response.response_metadata.get("finish_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )
