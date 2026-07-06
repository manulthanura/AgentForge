"""Slack and email notifiers, both implementing the Notifier port."""

from __future__ import annotations

import httpx
import pytest

from notification.application.ports import NotificationError, Notifier
from notification.application.send_notification import SendNotificationUseCase
from notification.domain.models import Channel, NotificationMessage
from notification.infrastructure.email_notifier import EmailNotifier
from notification.infrastructure.slack_notifier import SlackNotifier

MESSAGE = NotificationMessage(
    channel=Channel.SLACK, subject="Approval needed", body="Issue #42 diff ..."
)


# --- Slack ----------------------------------------------------------------


class _StubHttpx:
    def __init__(self, status=200):
        self.status = status
        self.url = None
        self.json_body = None

    def post(self, url, json=None):
        self.url = url
        self.json_body = json
        request = httpx.Request("POST", url)
        return httpx.Response(self.status, request=request)


def test_slack_notifier_posts_to_webhook():
    stub = _StubHttpx()
    notifier = SlackNotifier(
        "https://hooks.slack.example/T000", "#agent-approvals", client=stub
    )
    assert isinstance(notifier, Notifier)

    notifier.send(MESSAGE)

    assert stub.url == "https://hooks.slack.example/T000"
    assert stub.json_body["channel"] == "#agent-approvals"
    assert "Approval needed" in stub.json_body["text"]
    assert "Issue #42" in stub.json_body["text"]


def test_slack_http_failure_becomes_notification_error():
    notifier = SlackNotifier("https://hooks.slack.example/T000", client=_StubHttpx(500))
    with pytest.raises(NotificationError, match="Slack delivery failed"):
        notifier.send(MESSAGE)


# --- Email ------------------------------------------------------------------


class _StubSmtp:
    sent = []
    fail = False

    def __init__(self, host, port):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send_message(self, email):
        if _StubSmtp.fail:
            raise OSError("connection refused")
        _StubSmtp.sent.append(email)


@pytest.fixture(autouse=True)
def _reset_smtp():
    _StubSmtp.sent = []
    _StubSmtp.fail = False


def _email_notifier() -> EmailNotifier:
    return EmailNotifier(
        host="smtp.example.com",
        port=587,
        sender="agentforge@example.com",
        recipient="dev@example.com",
        smtp_factory=_StubSmtp,
    )


def test_email_notifier_sends_message():
    notifier = _email_notifier()
    assert isinstance(notifier, Notifier)
    message = NotificationMessage(
        channel=Channel.EMAIL, subject="Approval needed", body="Diff attached"
    )

    notifier.send(message)

    email = _StubSmtp.sent[0]
    assert email["Subject"] == "Approval needed"
    assert email["From"] == "agentforge@example.com"
    assert email["To"] == "dev@example.com"
    assert "Diff attached" in email.get_content()


def test_email_failure_becomes_notification_error():
    _StubSmtp.fail = True
    with pytest.raises(NotificationError, match="Email delivery failed"):
        _email_notifier().send(
            NotificationMessage(channel=Channel.EMAIL, subject="s", body="b")
        )


# --- Routing use case -------------------------------------------------------


def test_send_notification_routes_by_channel():
    stub = _StubHttpx()
    use_case = SendNotificationUseCase(
        [SlackNotifier("https://hooks.slack.example/T000", client=stub), _email_notifier()]
    )
    assert use_case.channels == {Channel.SLACK, Channel.EMAIL}

    use_case.execute(MESSAGE)
    assert stub.json_body is not None
    assert _StubSmtp.sent == []


def test_send_notification_unconfigured_channel_raises():
    use_case = SendNotificationUseCase([])
    with pytest.raises(NotificationError, match="No notifier configured"):
        use_case.execute(MESSAGE)
