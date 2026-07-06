"""Retrying decorator for any LLMProvider (R-02).

Wraps a concrete adapter and retries transient failures with exponential
backoff (2s/4s/8s by default), honoring server Retry-After on rate limits.
Deterministic errors (bad request, auth, refusal) are never retried.
"""

from __future__ import annotations

import time
from typing import Callable

from ..resilience.retry import RetryPolicy, retry_call
from .port import LLMProvider, LLMResponse, LLMUnavailableError, Message


class RetryingLLMProvider(LLMProvider):
    name = "retrying"
    default_model = "delegated"

    def __init__(
        self,
        inner: LLMProvider,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.inner = inner
        self.policy = policy or RetryPolicy()
        self._sleep = sleep
        # Proxy identity so callers (health checks, logs) see the real adapter.
        self.name = inner.name
        self.default_model = inner.default_model
        self.model = getattr(inner, "model", inner.default_model)

    def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        return retry_call(
            lambda: self.inner.complete(
                messages, system=system, max_tokens=max_tokens, json_mode=json_mode
            ),
            policy=self.policy,
            retryable=(LLMUnavailableError,),
            retry_after=lambda exc: getattr(exc, "retry_after", None),
            sleep=self._sleep,
        )
