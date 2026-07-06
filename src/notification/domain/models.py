"""Notification domain model (delivery arrives with Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Channel(StrEnum):
    SLACK = "slack"
    EMAIL = "email"
    WEB = "web"


@dataclass(frozen=True)
class NotificationMessage:
    channel: Channel
    subject: str
    body: str
