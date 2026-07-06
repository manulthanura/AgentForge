"""LangGraph runtime state carried through the state machine.

This TypedDict is a LangGraph implementation detail; the durable, queryable
view of a workflow is the AgentWorkflow aggregate in the domain layer.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    workflow_id: str
    # The GitHub issue being processed: {number, title, body, labels}.
    issue: dict[str, Any]
    # Local checkout the agent may search. Defaults to cwd.
    workspace: str

    # Output of the analyze node (IssueAnalysis.to_dict()).
    analysis: dict[str, Any]
    classification: str  # IssueType value

    # Decision log — every router decision with its reasoning (appended).
    decisions: Annotated[list[dict[str, Any]], operator.add]
    # Tool execution results (appended).
    tool_results: Annotated[list[dict[str, Any]], operator.add]

    # Router output consumed by the conditional edge.
    next_action: str
    next_args: dict[str, Any]

    status: str  # WorkflowStatus value
    error: str | None
    step_count: int
    # Consecutive failed tool executions; reset on success. The router
    # escalates when this hits the compound-failure cap (R-09).
    consecutive_failures: int

    # Human-in-the-loop approval gate (Phase 3).
    pending_approval: dict[str, Any]  # payload shown to the reviewer
    approval_decision: str  # "approved" | "rejected"
    approval_feedback: str  # human feedback on rejection
    approval_retry_count: int
