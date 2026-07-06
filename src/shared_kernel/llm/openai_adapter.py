"""OpenAI adapter for the LLMProvider port."""

from __future__ import annotations

import openai

from ..config.settings import Settings
from .port import (
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMUnavailableError,
    Message,
)


def _retry_after_header(exc: openai.APIStatusError) -> float | None:
    try:
        value = exc.response.headers.get("retry-after")
        return float(value) if value is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._client = openai.OpenAI(api_key=settings.openai_api_key)

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        chat_messages: list[dict] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(
            {"role": m["role"], "content": m["content"]} for m in messages
        )
        kwargs: dict = {
            "model": self.model,
            "messages": chat_messages,
            "max_completion_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.APIStatusError as exc:
            status = exc.status_code
            if status == 429:
                raise LLMRateLimitError(
                    f"OpenAI rate limited: {exc}",
                    retry_after=_retry_after_header(exc),
                ) from exc
            if status >= 500:
                raise LLMUnavailableError(
                    f"OpenAI unavailable ({status}): {exc}"
                ) from exc
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(f"OpenAI unreachable: {exc}") from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=choice.message.content or "",
            model=response.model,
            stop_reason=choice.finish_reason,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            raw=response,
        )
