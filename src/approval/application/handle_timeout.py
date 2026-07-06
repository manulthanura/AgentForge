"""Use case: remind, then expire, approval requests nobody answered.

Per the approval feature: send a reminder after ``reminder_hours``; after
``timeout_hours`` mark the request timed out (the workflow stays paused and
its checkpoint remains valid — R-07).
"""

from __future__ import annotations

import datetime
import logging

from notification.application.send_notification import SendNotificationUseCase
from notification.domain.models import Channel, NotificationMessage

from ..domain.models import ApprovalRequest
from .ports import ApprovalRepository

logger = logging.getLogger(__name__)


class HandleTimeoutUseCase:
    def __init__(
        self,
        repository: ApprovalRepository,
        send_notification: SendNotificationUseCase | None = None,
        reminder_hours: int = 48,
        timeout_hours: int = 72,
        channel: Channel = Channel.SLACK,
    ):
        self._repository = repository
        self._send_notification = send_notification
        self._reminder_hours = reminder_hours
        self._timeout_hours = timeout_hours
        self._channel = channel

    def execute(
        self, now: datetime.datetime | None = None
    ) -> dict[str, list[str]]:
        """Sweep pending requests; returns {"reminded": [...], "timed_out": [...]}."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        reminded: list[str] = []
        timed_out: list[str] = []
        for request in self._repository.list_pending():
            age = request.age_hours(now)
            if age >= self._timeout_hours:
                self._repository.save(request.time_out())
                timed_out.append(request.workflow_id)
                self._notify(
                    f"Approval timed out: workflow {request.workflow_id}",
                    f"No response after {self._timeout_hours}h. The workflow is "
                    "parked; its checkpoint remains valid for manual resume.",
                )
            elif age >= self._reminder_hours and request.reminded_at is None:
                self._repository.save(request.with_reminder(now))
                reminded.append(request.workflow_id)
                self._notify(
                    f"Reminder: workflow {request.workflow_id} awaits approval",
                    f"Pending for {age:.0f}h. Please approve or reject.",
                )
        return {"reminded": reminded, "timed_out": timed_out}

    def _notify(self, subject: str, body: str) -> None:
        if not self._send_notification:
            return
        try:
            self._send_notification.execute(
                NotificationMessage(channel=self._channel, subject=subject, body=body)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Timeout notification failed")
