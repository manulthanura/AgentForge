"""Corrupted checkpoint handling (R-08)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from workflow_orchestration.infrastructure.langgraph.engine import (
    LangGraphWorkflowEngine,
)
from workflow_orchestration.infrastructure.postgres_workflow_repo import (
    CorruptedWorkflowStateError,
    PostgresWorkflowRepository,
)

VALID_STATE = {
    "workflow_id": "wf-42",
    "status": "awaiting_approval",
    "issue": {"number": 42},
    "decisions": [{"node": "route", "action": "finish"}],
}

CORRUPT_STATE = {
    "workflow_id": "wf-42",
    "status": "☠️not-a-status☠️",
    "issue": "corrupted-into-a-string",
    "decisions": "not-a-list",
}


class _StubGraph:
    """Mimics a compiled LangGraph's checkpoint accessors."""

    def __init__(self, current, history):
        self.current = current
        self.history = history

    def get_state(self, config):
        return SimpleNamespace(values=self.current)

    def get_state_history(self, config):
        return iter(SimpleNamespace(values=v) for v in self.history)


def test_corrupted_checkpoint_falls_back_to_last_valid():
    engine = LangGraphWorkflowEngine(
        _StubGraph(current=CORRUPT_STATE, history=[CORRUPT_STATE, VALID_STATE])
    )
    state = engine.get_state("wf-42")
    assert state == VALID_STATE  # skipped the corrupt snapshot


def test_valid_checkpoint_returned_directly_without_history_walk():
    class _NoHistory(_StubGraph):
        def get_state_history(self, config):
            raise AssertionError("history must not be consulted")

    engine = LangGraphWorkflowEngine(_NoHistory(current=VALID_STATE, history=[]))
    assert engine.get_state("wf-42") == VALID_STATE


def test_no_valid_checkpoint_yields_empty_state():
    engine = LangGraphWorkflowEngine(
        _StubGraph(current=CORRUPT_STATE, history=[CORRUPT_STATE])
    )
    assert engine.get_state("wf-42") == {}


def test_unknown_thread_returns_empty_without_history_walk():
    engine = LangGraphWorkflowEngine(_StubGraph(current={}, history=[]))
    assert engine.get_state("ghost") == {}


# --- Workflow index row corruption ------------------------------------------


def test_repo_detects_invalid_status():
    row = {
        "workflow_id": "wf-42",
        "issue": {"number": 42},
        "status": "☠️not-a-status☠️",
        "classification": None,
    }
    with pytest.raises(CorruptedWorkflowStateError, match="invalid status"):
        PostgresWorkflowRepository._to_aggregate(row)


def test_repo_detects_non_object_issue_payload():
    row = {
        "workflow_id": "wf-42",
        "issue": "corrupted",
        "status": "done",
        "classification": "bug",
    }
    with pytest.raises(CorruptedWorkflowStateError, match="issue payload"):
        PostgresWorkflowRepository._to_aggregate(row)


def test_repo_accepts_valid_row():
    row = {
        "workflow_id": "wf-42",
        "issue": {"number": 42},
        "status": "done",
        "classification": "bug",
    }
    workflow = PostgresWorkflowRepository._to_aggregate(row)
    assert workflow.workflow_id == "wf-42"
