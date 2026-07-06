"""Approval use cases: request, respond, and timeout sweeps."""

from __future__ import annotations

import datetime

import pytest

from approval.application.handle_response import (
    HandleApprovalResponseUseCase,
    UnknownApprovalError,
)
from approval.application.handle_timeout import HandleTimeoutUseCase
from approval.application.ports import WorkflowResumer
from approval.application.request_approval import RequestApprovalUseCase
from approval.domain.models import ApprovalRequest, ApprovalStatus
from approval.infrastructure.in_memory_repo import InMemoryApprovalRepository
from notification.application.send_notification import SendNotificationUseCase
from notification.application.ports import Notifier
from notification.domain.models import Channel


class CapturingNotifier(Notifier):
    channel = Channel.SLACK

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class FakeResumer(WorkflowResumer):
    def __init__(self):
        self.calls = []

    def execute(self, workflow_id, decision):
        self.calls.append((workflow_id, decision))
        return {"status": "done" if decision["approved"] else "routing"}


PAYLOAD = {
    "workflow_id": "issue-42",
    "action": "finalize_workflow",
    "issue": {"number": 42, "title": "Login fails with '+'"},
    "summary": "login failure with special characters",
    "diffs": [{"path": "src/auth/login.py", "diff": "+sanitize(email)"}],
    "test_summary": "5 passed",
    "risk": "severity=high, area=authentication",
}


def test_request_approval_persists_and_notifies_reviewer_elements():
    repo = InMemoryApprovalRepository()
    notifier = CapturingNotifier()
    use_case = RequestApprovalUseCase(repo, SendNotificationUseCase([notifier]))

    request = use_case.execute(PAYLOAD)

    assert repo.get("issue-42").status is ApprovalStatus.PENDING
    assert request.action == "finalize_workflow"
    # Slack message contains every element from the approval feature table.
    body = notifier.messages[0].body
    assert "Issue #42" in body  # issue summary
    assert "+sanitize(email)" in body  # proposed diff
    assert "5 passed" in body  # test results
    assert "severity=high" in body  # risk assessment
    assert "Approve / Reject" in body  # action buttons hint


def test_request_approval_survives_notification_outage():
    class BrokenNotifier(CapturingNotifier):
        def send(self, message):
            raise RuntimeError("slack down")

    repo = InMemoryApprovalRepository()
    use_case = RequestApprovalUseCase(
        repo, SendNotificationUseCase([BrokenNotifier()])
    )
    use_case.execute(PAYLOAD)  # must not raise
    assert repo.get("issue-42").status is ApprovalStatus.PENDING


def test_approval_resumes_workflow_and_records_decision():
    repo = InMemoryApprovalRepository()
    repo.save(ApprovalRequest(workflow_id="issue-42", action="finalize_workflow"))
    resumer = FakeResumer()

    final = HandleApprovalResponseUseCase(resumer, repo).execute(
        "issue-42", approved=True
    )

    assert final["status"] == "done"
    assert resumer.calls == [("issue-42", {"approved": True, "feedback": ""})]
    assert repo.get("issue-42").status is ApprovalStatus.APPROVED


def test_rejection_carries_feedback_to_the_workflow():
    repo = InMemoryApprovalRepository()
    repo.save(ApprovalRequest(workflow_id="issue-42", action="finalize_workflow"))
    resumer = FakeResumer()

    HandleApprovalResponseUseCase(resumer, repo).execute(
        "issue-42", approved=False, feedback="Try a different approach"
    )

    assert resumer.calls[0][1] == {
        "approved": False,
        "feedback": "Try a different approach",
    }
    stored = repo.get("issue-42")
    assert stored.status is ApprovalStatus.REJECTED
    assert stored.feedback == "Try a different approach"


def test_unknown_or_settled_approval_is_rejected():
    repo = InMemoryApprovalRepository()
    use_case = HandleApprovalResponseUseCase(FakeResumer(), repo)
    with pytest.raises(UnknownApprovalError):
        use_case.execute("ghost", approved=True)

    repo.save(
        ApprovalRequest(
            workflow_id="settled",
            action="finalize_workflow",
            status=ApprovalStatus.APPROVED,
        )
    )
    with pytest.raises(UnknownApprovalError, match="already approved"):
        use_case.execute("settled", approved=True)


def test_timeout_sweep_reminds_then_expires():
    now = datetime.datetime.now(datetime.timezone.utc)
    repo = InMemoryApprovalRepository()
    repo.save(
        ApprovalRequest(
            workflow_id="fresh",
            action="a",
            requested_at=now - datetime.timedelta(hours=1),
        )
    )
    repo.save(
        ApprovalRequest(
            workflow_id="stale",
            action="a",
            requested_at=now - datetime.timedelta(hours=50),
        )
    )
    repo.save(
        ApprovalRequest(
            workflow_id="dead",
            action="a",
            requested_at=now - datetime.timedelta(hours=80),
        )
    )
    notifier = CapturingNotifier()
    sweep = HandleTimeoutUseCase(
        repo,
        SendNotificationUseCase([notifier]),
        reminder_hours=48,
        timeout_hours=72,
    )

    result = sweep.execute(now)

    assert result == {"reminded": ["stale"], "timed_out": ["dead"]}
    assert repo.get("dead").status is ApprovalStatus.TIMED_OUT
    assert repo.get("stale").status is ApprovalStatus.PENDING
    assert repo.get("stale").reminded_at is not None
    assert len(notifier.messages) == 2

    # Second sweep: no duplicate reminders.
    assert sweep.execute(now) == {"reminded": [], "timed_out": []}
