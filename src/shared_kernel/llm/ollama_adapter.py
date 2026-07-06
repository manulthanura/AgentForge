"""Ollama (local LLM) adapter for the LLMProvider port.

Talks to the Ollama HTTP API directly (POST /api/chat) so no extra SDK is
required beyond httpx.
"""

from __future__ import annotations

import httpx

from ..config.settings import Settings
from .port import (
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMUnavailableError,
    Message,
)


class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "llama3.1"

    def __init__(self, settings: Settings, model: str | None = None):
        self.model = settings.llm_model or model or self.default_model
        self.base_url = settings.ollama_base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=120.0)

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
        payload: dict = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                raise LLMRateLimitError(f"Ollama rate limited: {exc}") from exc
            if status >= 500:
                raise LLMUnavailableError(
                    f"Ollama unavailable ({status}): {exc}"
                ) from exc
            raise LLMError(f"Ollama request failed: {exc}") from exc
        except httpx.HTTPError as exc:
            # Connection/timeout problems are transient by nature.
            raise LLMUnavailableError(f"Ollama unreachable: {exc}") from exc

        data = response.json()
        return LLMResponse(
            text=data.get("message", {}).get("content", ""),
            model=data.get("model", self.model),
            stop_reason=data.get("done_reason"),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            raw=data,
        )
