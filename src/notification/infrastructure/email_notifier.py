"""Email delivery via SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Callable

from ..application.ports import NotificationError, Notifier
from ..domain.models import Channel, NotificationMessage

# Factory indirection so tests can inject a stub SMTP client.
SmtpFactory = Callable[[str, int], smtplib.SMTP]


class EmailNotifier(Notifier):
    channel = Channel.EMAIL

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        recipient: str,
        smtp_factory: SmtpFactory = smtplib.SMTP,
    ):
        self._host = host
        self._port = port
        self._sender = sender
        self._recipient = recipient
        self._smtp_factory = smtp_factory

    def send(self, message: NotificationMessage) -> None:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = self._sender
        email["To"] = self._recipient
        email.set_content(message.body)
        try:
            with self._smtp_factory(self._host, self._port) as smtp:
                smtp.send_message(email)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotificationError(f"Email delivery failed: {exc}") from exc
