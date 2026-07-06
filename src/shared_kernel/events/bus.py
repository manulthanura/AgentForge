"""Minimal in-process domain event bus.

Handlers must never break the publishing workflow: exceptions are captured
and logged, not propagated.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

from .events import DomainEvent

logger = logging.getLogger(__name__)

Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for event_type, handlers in self._handlers.items():
            if isinstance(event, event_type):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Event handler failed for %s", type(event).__name__
                        )
