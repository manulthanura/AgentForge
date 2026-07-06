"""Use case: route a message to the notifier for its channel."""

from __future__ import annotations

from ..domain.models import Channel, NotificationMessage
from .ports import NotificationError, Notifier


class SendNotificationUseCase:
    def __init__(self, notifiers: list[Notifier]):
        self._by_channel: dict[Channel, Notifier] = {
            n.channel: n for n in notifiers
        }

    @property
    def channels(self) -> set[Channel]:
        return set(self._by_channel)

    def execute(self, message: NotificationMessage) -> None:
        notifier = self._by_channel.get(message.channel)
        if notifier is None:
            raise NotificationError(
                f"No notifier configured for channel {message.channel.value!r}"
            )
        notifier.send(message)
