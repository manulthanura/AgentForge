"""Shared helpers for adapters built on LangChain chat model wrappers.

Azure OpenAI, Gemini, and Hugging Face all go through LangChain's
provider-agnostic ``BaseChatModel`` interface (``langchain-openai``,
``langchain-google-genai``, ``langchain-huggingface``) rather than a raw
vendor SDK, so message conversion, token-usage extraction, and error mapping
live here once instead of being duplicated per adapter.
"""

from __future__ import annotations

from typing import NoReturn

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .port import LLMError, LLMRateLimitError, LLMUnavailableError, Message


def to_langchain_messages(
    messages: list[Message], system: str | None
) -> list[BaseMessage]:
    lc_messages: list[BaseMessage] = []
    if system:
        lc_messages.append(SystemMessage(content=system))
    for m in messages:
        if m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))
        else:
            lc_messages.append(HumanMessage(content=m["content"]))
    return lc_messages


def response_text(response: AIMessage) -> str:
    """Extract plain text regardless of whether ``.content`` is a string or
    a list of content blocks (e.g. Anthropic extended-thinking blocks)."""
    return response.text or ""


def token_usage(response: AIMessage) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return None, None
    return usage.get("input_tokens"), usage.get("output_tokens")


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _openai_style_error_payload(exc: Exception) -> dict | None:
    """``langchain-openai`` raises ``ValueError(error_dict)`` for
    OpenAI-compatible APIs (e.g. OpenRouter) that return HTTP 200 with a
    null ``choices`` and an embedded ``error`` instead of an HTTP error
    status — this recovers that payload so it maps to a typed error rather
    than a generic, non-retryable ``LLMError``."""
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], dict):
        payload = exc.args[0]
        if "message" in payload:
            return payload
    return None


def raise_as_llm_error(provider_label: str, exc: Exception) -> NoReturn:
    """Map a LangChain chat model invocation failure onto the port's typed
    error hierarchy, keyed off HTTP status where the underlying SDK exposes
    one — works across the openai, anthropic, google-genai, and
    huggingface_hub client exceptions LangChain surfaces unwrapped."""
    payload = _openai_style_error_payload(exc)
    if payload is not None:
        code = payload.get("code")
        message = payload.get("message", exc)
        if code == 429:
            raise LLMRateLimitError(
                f"{provider_label} rate limited: {message}"
            ) from exc
        raise LLMUnavailableError(
            f"{provider_label} returned no choices: {message}"
        ) from exc

    status = _status_code(exc)
    if status == 429:
        raise LLMRateLimitError(
            f"{provider_label} rate limited: {exc}", retry_after=_retry_after(exc)
        ) from exc
    if status is not None and status >= 500:
        raise LLMUnavailableError(
            f"{provider_label} unavailable ({status}): {exc}"
        ) from exc
    if isinstance(exc, (ConnectionError, TimeoutError, httpx.TransportError)):
        # Most SDKs normalize connection failures to a builtin
        # ConnectionError; Ollama's streaming path can leak a raw
        # httpx.TransportError (ConnectError/ReadTimeout/...) unwrapped.
        raise LLMUnavailableError(f"{provider_label} unreachable: {exc}") from exc
    raise LLMError(f"{provider_label} request failed: {exc}") from exc
