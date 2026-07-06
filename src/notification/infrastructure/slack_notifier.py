"""Slack delivery via an incoming webhook URL."""

from __future__ import annotations

import httpx

from ..application.ports import NotificationError, Notifier
from ..domain.models import Channel, NotificationMessage


class SlackNotifier(Notifier):
    channel = Channel.SLACK

    def __init__(
        self,
        webhook_url: str,
        default_channel: str = "#agent-approvals",
        client: httpx.Client | None = None,
    ):
        self._webhook_url = webhook_url
        self._default_channel = default_channel
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, message: NotificationMessage) -> None:
        payload = {
            "channel": self._default_channel,
            "text": f"*{message.subject}*\n{message.body}",
        }
        try:
            response = self._client.post(self._webhook_url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(f"Slack delivery failed: {exc}") from exc
