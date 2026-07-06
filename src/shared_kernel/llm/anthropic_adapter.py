"""Anthropic (Claude) adapter for the LLMProvider port."""

from __future__ import annotations

import anthropic

from ..config.settings import Settings
from .port import (
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMUnavailableError,
    Message,
)


def _retry_after_header(exc: anthropic.APIStatusError) -> float | None:
    try:
        value = exc.response.headers.get("retry-after")
        return float(value) if value is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-4-8"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

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
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": m["role"], "content": m["content"]} for m in messages
            ],
            "thinking": {"type": "adaptive"},
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            status = exc.status_code
            if status == 429:
                raise LLMRateLimitError(
                    f"Anthropic rate limited: {exc}",
                    retry_after=_retry_after_header(exc),
                ) from exc
            if status >= 500 or status == 529:  # 529 = overloaded
                raise LLMUnavailableError(
                    f"Anthropic unavailable ({status}): {exc}"
                ) from exc
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError(f"Anthropic unreachable: {exc}") from exc
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("Anthropic declined the request (stop_reason=refusal)")

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return LLMResponse(
            text=text,
            model=response.model,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            raw=response,
        )
