"""Generic retry with exponential backoff (R-02, R-03).

Default policy matches the error-recovery feature: 3 retries with delays of
2s, 4s, 8s. A server-provided Retry-After always overrides the computed
backoff. ``sleep`` is injectable so tests never actually wait.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 2.0
    factor: float = 2.0
    max_delay: float = 60.0

    def delay_for(self, retry_number: int) -> float:
        """Backoff before the Nth retry (1-based): 2s, 4s, 8s, ..."""
        return min(self.base_delay * self.factor ** (retry_number - 1), self.max_delay)


def retry_call(
    fn: Callable[[], Any],
    *,
    policy: RetryPolicy | None = None,
    retryable: tuple[type[BaseException], ...] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
    retry_after: Callable[[BaseException], float | None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call ``fn``, retrying transient failures with exponential backoff.

    - ``retryable``: exception types that may be retried at all.
    - ``should_retry``: optional predicate to narrow retryable instances
      (e.g. only HTTP 429/5xx).
    - ``retry_after``: optional extractor for a server-provided cooldown,
      which overrides the computed backoff (R-03).
    """
    policy = policy or RetryPolicy()
    retries = 0
    while True:
        try:
            return fn()
        except retryable as exc:
            if should_retry is not None and not should_retry(exc):
                raise
            retries += 1
            if retries > policy.max_retries:
                raise
            server_delay = retry_after(exc) if retry_after else None
            delay = server_delay if server_delay is not None else policy.delay_for(retries)
            logger.warning(
                "Transient failure (%s); retry %d/%d in %.1fs",
                exc,
                retries,
                policy.max_retries,
                delay,
            )
            sleep(delay)
