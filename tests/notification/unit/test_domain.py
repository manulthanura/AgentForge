from notification.domain.models import Channel, NotificationMessage


def test_message_holds_channel_and_content():
    message = NotificationMessage(
        channel=Channel.SLACK, subject="Approval needed", body="Issue #42"
    )
    assert message.channel is Channel.SLACK
    assert Channel("email") is Channel.EMAIL
