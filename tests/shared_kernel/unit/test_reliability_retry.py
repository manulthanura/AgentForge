"""Retry core + RetryingLLMProvider: backoff, Retry-After, recovery (R-02)."""

from __future__ import annotations

import pytest

from shared_kernel.llm import (
    LLMError,
    LLMRateLimitError,
    LLMResponse,
    LLMUnavailableError,
    RetryingLLMProvider,
)
from shared_kernel.resilience import RetryPolicy, retry_call

from tests.support.fakes import FakeProvider, FlakyProvider

MESSAGES = [{"role": "user", "content": "hi"}]


# --- RetryPolicy / retry_call ------------------------------------------------


def test_policy_delays_follow_feature_table():
    policy = RetryPolicy()
    assert [policy.delay_for(n) for n in (1, 2, 3)] == [2.0, 4.0, 8.0]


def test_policy_caps_at_max_delay():
    assert RetryPolicy(max_delay=5.0).delay_for(3) == 5.0


def test_retry_call_recovers_after_transient_failures():
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = retry_call(
        flaky, retryable=(ValueError,), sleep=sleeps.append
    )
    assert result == "ok"
    assert sleeps == [2.0, 4.0]  # exponential backoff between attempts


def test_retry_call_exhausts_and_reraises():
    sleeps: list[float] = []

    def always_broken():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        retry_call(always_broken, retryable=(ValueError,), sleep=sleeps.append)
    assert sleeps == [2.0, 4.0, 8.0]  # three retries, then give up


def test_retry_call_respects_should_retry_predicate():
    sleeps: list[float] = []

    def fatal():
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        retry_call(
            fatal,
            retryable=(ValueError,),
            should_retry=lambda exc: "transient" in str(exc),
            sleep=sleeps.append,
        )
    assert sleeps == []  # non-retryable: no backoff, immediate raise


def test_retry_after_overrides_backoff():
    sleeps: list[float] = []
    calls = {"n": 0}

    class Cooldown(Exception):
        retry_after = 9.5

    def rate_limited():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Cooldown()
        return "ok"

    retry_call(
        rate_limited,
        retryable=(Cooldown,),
        retry_after=lambda exc: exc.retry_after,
        sleep=sleeps.append,
    )
    assert sleeps == [9.5]


# --- RetryingLLMProvider ------------------------------------------------------


def test_llm_outage_then_recovery(sample_issue):
    """R-02: two 503s, then the API recovers — the call succeeds."""
    sleeps: list[float] = []
    flaky = FlakyProvider(
        failures=[
            LLMUnavailableError("503 service unavailable"),
            LLMUnavailableError("503 service unavailable"),
        ],
        responses=["recovered"],
    )
    provider = RetryingLLMProvider(flaky, sleep=sleeps.append)

    response = provider.complete(MESSAGES)

    assert isinstance(response, LLMResponse)
    assert response.text == "recovered"
    assert flaky.attempts == 3
    assert sleeps == [2.0, 4.0]


def test_llm_rate_limit_uses_server_cooldown():
    sleeps: list[float] = []
    flaky = FlakyProvider(
        failures=[LLMRateLimitError("429", retry_after=7.0)],
        responses=["ok"],
    )
    RetryingLLMProvider(flaky, sleep=sleeps.append).complete(MESSAGES)
    assert sleeps == [7.0]


def test_llm_outage_exhausts_retries():
    sleeps: list[float] = []
    flaky = FlakyProvider(
        failures=[LLMUnavailableError("503") for _ in range(10)]
    )
    with pytest.raises(LLMUnavailableError):
        RetryingLLMProvider(flaky, sleep=sleeps.append).complete(MESSAGES)
    assert sleeps == [2.0, 4.0, 8.0]
    assert flaky.attempts == 4  # initial + 3 retries


def test_deterministic_llm_errors_are_never_retried():
    sleeps: list[float] = []
    flaky = FlakyProvider(failures=[LLMError("400 bad request")])
    with pytest.raises(LLMError):
        RetryingLLMProvider(flaky, sleep=sleeps.append).complete(MESSAGES)
    assert sleeps == []
    assert flaky.attempts == 1


def test_retrying_provider_proxies_identity():
    provider = RetryingLLMProvider(FakeProvider())
    assert provider.name == "fake"
    assert provider.model == "fake-model-1"
