"""OpenRouter adapter for the LLMProvider port.

OpenRouter exposes an OpenAI-compatible Chat Completions API, so this reuses
the `openai` SDK pointed at OpenRouter's base URL instead of pulling in a
separate client. Model names are OpenRouter slugs (e.g. "openai/gpt-4o",
"anthropic/claude-sonnet-4.5") since OpenRouter routes to many upstream
providers behind one key.
"""

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
        self._client = openai.OpenAI(
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
        chat_messages: list[dict] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(
            {"role": m["role"], "content": m["content"]} for m in messages
        )
        kwargs: dict = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.APIStatusError as exc:
            status = exc.status_code
            if status == 429:
                raise LLMRateLimitError(
                    f"OpenRouter rate limited: {exc}",
                    retry_after=_retry_after_header(exc),
                ) from exc
            if status >= 500:
                raise LLMUnavailableError(
                    f"OpenRouter unavailable ({status}): {exc}"
                ) from exc
            raise LLMError(f"OpenRouter request failed: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(f"OpenRouter unreachable: {exc}") from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc

        if not response.choices:
            # OpenRouter can return HTTP 200 with `choices: null` and an
            # `error` field when the routed upstream provider fails (common
            # on free-tier models) instead of raising an HTTP error status.
            error = getattr(response, "error", None)
            detail = error.get("message") if isinstance(error, dict) else error
            raise LLMUnavailableError(
                "OpenRouter returned no choices"
                + (f": {detail}" if detail else " (upstream provider unavailable)")
            )

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
