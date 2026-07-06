"""Use case: record an approval request and notify a human reviewer.

The notification carries everything a reviewer needs to decide within 30
seconds (U-01): issue summary, proposed diffs, test results, risk notes.
Notification failure never blocks the workflow — the request is still
persisted and the workflow stays safely paused.
"""

from __future__ import annotations

import logging
from typing import Any

from notification.application.send_notification import SendNotificationUseCase
from notification.domain.models import Channel, NotificationMessage

from ..domain.models import ApprovalRequest
from .ports import ApprovalRepository

logger = logging.getLogger(__name__)


class RequestApprovalUseCase:
    def __init__(
        self,
        repository: ApprovalRepository,
        send_notification: SendNotificationUseCase | None = None,
        channel: Channel = Channel.SLACK,
    ):
        self._repository = repository
        self._send_notification = send_notification
        self._channel = channel

    def execute(self, payload: dict[str, Any]) -> ApprovalRequest:
        request = ApprovalRequest(
            workflow_id=str(payload.get("workflow_id", "")),
            action=str(payload.get("action", "finalize_workflow")),
        )
        self._repository.save(request)

        if self._send_notification:
            try:
                self._send_notification.execute(self._build_message(payload))
            except Exception:  # noqa: BLE001 — delivery must not break the pause
                logger.exception(
                    "Approval notification failed for %s", request.workflow_id
                )
        return request

    def _build_message(self, payload: dict[str, Any]) -> NotificationMessage:
        issue = payload.get("issue", {})
        lines = [
            f"Issue #{issue.get('number', '?')}: {issue.get('title', '')}",
            f"Summary: {payload.get('summary', 'n/a')}",
            "",
            "Proposed changes:",
        ]
        for diff in payload.get("diffs", []) or [{"path": "(none)", "diff": ""}]:
            lines.append(f"--- {diff.get('path', '?')} ---")
            lines.append(diff.get("diff", "")[:2000])
        lines += [
            "",
            f"Test results: {payload.get('test_summary', 'not run')}",
            f"Risk assessment: {payload.get('risk', 'not assessed')}",
            "",
            "Respond with the Approve / Reject buttons.",
        ]
        return NotificationMessage(
            channel=self._channel,
            subject=f"Approval needed: workflow {payload.get('workflow_id', '?')}",
            body="\n".join(lines),
        )
