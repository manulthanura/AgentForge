"""Google Gemini adapter for the LLMProvider port.

Built on LangChain's ``langchain-google-genai`` integration
(``ChatGoogleGenerativeAI``), which wraps Google's ``google-genai`` SDK.
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from ..config.settings import Settings
from .langchain_support import (
    raise_as_llm_error,
    response_text,
    to_langchain_messages,
    token_usage,
)
from .port import LLMProvider, LLMResponse, Message


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._chat_model = ChatGoogleGenerativeAI(
            model=self.model, google_api_key=settings.google_api_key
        )

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        # json_mode stays prompt-level here (complete_json's instruction) —
        # Gemini's native response_mime_type enforcement isn't wired to
        # avoid coupling to a specific langchain-google-genai kwarg version.
        lc_messages = to_langchain_messages(messages, system)
        try:
            response = self._chat_model.bind(max_output_tokens=max_tokens).invoke(
                lc_messages
            )
        except Exception as exc:
            raise_as_llm_error("Gemini", exc)

        input_tokens, output_tokens = token_usage(response)
        return LLMResponse(
            text=response_text(response),
            model=response.response_metadata.get("model_name", self.model),
            stop_reason=response.response_metadata.get("finish_reason"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response,
        )
