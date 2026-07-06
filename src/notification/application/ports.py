"""Ports (interfaces) the notification use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Channel, NotificationMessage


class NotificationError(RuntimeError):
    """Raised when a message cannot be delivered."""


class Notifier(ABC):
    """One delivery backend (Slack, email, ...)."""

    channel: Channel

    @abstractmethod
    def send(self, message: NotificationMessage) -> None:
        """Deliver the message. Raises NotificationError on failure."""
