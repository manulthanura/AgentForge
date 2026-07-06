"""Provider-agnostic LLM port.

Every bounded context talks to this port only — never to a provider SDK
directly. Adapters live in sibling modules and are selected at runtime via
the LLM_PROVIDER env var (see factory.py).
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

# A chat message: {"role": "user" | "assistant", "content": "..."}
Message = dict[str, str]


@dataclass
class LLMResponse:
    """Normalized completion result, identical across providers."""

    text: str
    model: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: Any = field(default=None, repr=False)


class LLMError(RuntimeError):
    """Raised for provider failures, wrapping the provider-native exception."""


class LLMUnavailableError(LLMError):
    """Transient provider failure (5xx/overload/connection): retry sensible."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMRateLimitError(LLMUnavailableError):
    """HTTP 429; ``retry_after`` carries the server-requested cooldown."""


class LLMProvider(ABC):
    """Abstract chat-completion provider (the port).

    Adapters must set ``name`` (the LLM_PROVIDER value that selects them)
    and ``default_model``, and implement ``complete``.
    """

    name: ClassVar[str]
    default_model: ClassVar[str]

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Run a single chat completion and return the normalized response.

        ``json_mode`` asks the provider to emit a single JSON object; where a
        provider has native JSON enforcement it is used, otherwise it is
        prompt-level. Callers should still parse via ``complete_json``.
        """

    def complete_json(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Complete and parse the response as a JSON object."""
        instruction = (
            "Respond with a single valid JSON object only. "
            "No markdown fences, no prose before or after."
        )
        full_system = f"{system}\n\n{instruction}" if system else instruction
        response = self.complete(
            messages, system=full_system, max_tokens=max_tokens, json_mode=True
        )
        return extract_json(response.text)


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of model output, tolerating fences and prose."""
    candidate = text.strip()
    # Strip a ```json ... ``` fence if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} span in the text.
    start = candidate.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(candidate)):
            if candidate[i] == "{":
                depth += 1
            elif candidate[i] == "}":
                depth -= 1
                if depth == 0:
                    parsed = json.loads(candidate[start : i + 1])
                    if isinstance(parsed, dict):
                        return parsed
                    break
    raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
