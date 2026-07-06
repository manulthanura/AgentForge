"""Deterministic fake providers used across test suites. No network."""

from __future__ import annotations

from shared_kernel.llm import LLMError, LLMProvider, LLMResponse


class FakeProvider(LLMProvider):
    """Scripted provider: pops one canned response per complete() call."""

    name = "fake"
    default_model = "fake-model-1"

    def __init__(self, responses: list[str] | None = None):
        self.model = self.default_model
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def complete(self, messages, *, system=None, max_tokens=4096, json_mode=False):
        self.calls.append(
            {"messages": messages, "system": system, "json_mode": json_mode}
        )
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(text=text, model=self.model, stop_reason="end_turn")


class FailingProvider(LLMProvider):
    """Provider whose every call fails — for error-recovery paths."""

    name = "failing"
    default_model = "failing-model"

    def __init__(self):
        self.model = self.default_model

    def complete(self, messages, *, system=None, max_tokens=4096, json_mode=False):
        raise LLMError("simulated provider outage")


class FlakyProvider(LLMProvider):
    """Raises the queued exceptions first, then behaves like FakeProvider.

    Simulates a transient outage (e.g. two 503s, then recovery).
    """

    name = "flaky"
    default_model = "flaky-model"

    def __init__(self, failures: list[Exception], responses: list[str] | None = None):
        self.model = self.default_model
        self.failures = list(failures)
        self.inner = FakeProvider(responses=responses)
        self.attempts = 0

    def complete(self, messages, *, system=None, max_tokens=4096, json_mode=False):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.inner.complete(
            messages, system=system, max_tokens=max_tokens, json_mode=json_mode
        )
