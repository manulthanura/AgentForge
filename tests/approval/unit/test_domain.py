from approval.domain.models import ApprovalGate, ApprovalStatus


def test_gate_defaults():
    gate = ApprovalGate(action="create_pull_request")
    assert gate.timeout_hours == 72
    assert gate.is_irreversible()


def test_status_values():
    assert ApprovalStatus("pending") is ApprovalStatus.PENDING
    assert ApprovalStatus.TIMED_OUT.value == "timed_out"
