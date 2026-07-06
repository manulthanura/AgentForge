"""Retry wrapper for GitHub API calls (R-03: respect rate limits)."""

from __future__ import annotations

import time
from typing import Any, Callable

from github import GithubException

from .retry import RetryPolicy, retry_call

GITHUB_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, GithubException)
        and exc.status in GITHUB_RETRYABLE_STATUSES
    )


def _retry_after(exc: BaseException) -> float | None:
    headers = getattr(exc, "headers", None) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def retrying_github_call(
    fn: Callable[[], Any],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Run one GitHub API interaction, retrying 429/5xx with backoff."""
    return retry_call(
        fn,
        policy=policy,
        retryable=(GithubException,),
        should_retry=_retryable,
        retry_after=_retry_after,
        sleep=sleep,
    )
