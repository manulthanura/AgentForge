"""LangGraph node implementations.

Nodes coordinate other contexts' use cases and the router; all LLM access
happens behind the shared-kernel LLM port inside those use cases.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langgraph.types import interrupt

from issue_intake.application.analyze_issue import AnalyzeIssueUseCase
from issue_intake.domain.models import Issue
from shared_kernel.config.settings import Settings
from shared_kernel.events import (
    EventBus,
    IssueAnalyzed,
    ToolExecuted,
    WorkflowPaused,
)
from shared_kernel.llm import LLMError
from shared_kernel.observability import DecisionLogger

from ...application.routing import ESCALATE, FINISH, AgentRouter
from ...application.tools import ToolCatalog
from ...domain.models import Decision, WorkflowStatus
from .state import AgentState

logger = logging.getLogger(__name__)

# Called with the approval payload when a workflow pauses at the gate; the
# bootstrap wires approval's RequestApprovalUseCase in here.
ApprovalHook = Callable[[dict[str, Any]], Any]


def make_nodes(
    analyze_issue_uc: AnalyzeIssueUseCase,
    router: AgentRouter,
    catalog: ToolCatalog,
    settings: Settings,
    event_bus: EventBus | None = None,
    request_approval_hook: ApprovalHook | None = None,
    decision_logger: DecisionLogger | None = None,
) -> dict[str, Any]:
    """Build the node callables bound to their collaborators."""
    decision_logger = decision_logger or DecisionLogger()

    def _publish(event) -> None:
        if event_bus:
            event_bus.publish(event)

    def analyze_issue(state: AgentState) -> AgentState:
        issue = Issue.from_dict(state.get("issue", {}))
        try:
            analysis = analyze_issue_uc.execute(issue)
        except (LLMError, ValueError) as exc:
            return {
                "status": WorkflowStatus.ESCALATED.value,
                "error": f"Issue analysis failed: {exc}",
                "classification": "analysis_failed",
                "decisions": [
                    Decision(
                        node="analyze_issue", action=ESCALATE, reasoning=str(exc)
                    ).to_dict()
                ],
            }
        classification = analysis.issue_type.value
        _publish(
            IssueAnalyzed(
                workflow_id=state.get("workflow_id", ""),
                classification=classification,
            )
        )
        return {
            "analysis": analysis.to_dict(),
            "classification": classification,
            "status": WorkflowStatus.ROUTING.value,
            "decisions": [
                Decision(
                    node="analyze_issue",
                    action="classified",
                    reasoning=analysis.reasoning,
                    args={"result": classification},
                ).to_dict()
            ],
        }

    def request_clarification(state: AgentState) -> AgentState:
        return {
            "status": WorkflowStatus.AWAITING_CLARIFICATION.value,
            "decisions": [
                Decision(
                    node="request_clarification",
                    action="ask_reporter",
                    reasoning="Issue lacks reproduction steps / details.",
                ).to_dict()
            ],
        }

    def route(state: AgentState) -> AgentState:
        failures = state.get("consecutive_failures", 0)
        if failures >= settings.max_consecutive_failures:
            # R-09: cascading tool failures must not retry forever.
            return {
                "next_action": ESCALATE,
                "next_args": {},
                "decisions": [
                    Decision(
                        node="route",
                        action=ESCALATE,
                        reasoning=(
                            f"Compound failure: {failures} consecutive tool "
                            "failures; escalating to human review."
                        ),
                    ).to_dict()
                ],
            }
        steps = state.get("step_count", 0)
        if steps >= settings.max_agent_steps:
            return {
                "next_action": ESCALATE,
                "next_args": {},
                "decisions": [
                    Decision(
                        node="route",
                        action=ESCALATE,
                        reasoning=f"Step budget exhausted ({steps} steps).",
                    ).to_dict()
                ],
            }
        decision = router.decide(dict(state))
        return {
            "next_action": decision.action,
            "next_args": decision.args,
            "decisions": [
                Decision(
                    node="route",
                    action=decision.action,
                    reasoning=decision.reasoning,
                    args=decision.args,
                ).to_dict()
            ],
        }

    def execute_tool(state: AgentState) -> AgentState:
        name = state.get("next_action", "")
        args = dict(state.get("next_args", {}))
        # Inject state-derived context the LLM shouldn't have to supply.
        if name == "read_issue":
            args = {"issue": state.get("issue", {})}
        elif name == "search_code":
            args.setdefault("workspace", state.get("workspace", "."))
        elif name == "draft_fix":
            args["issue"] = state.get("issue", {})
            args["analysis"] = state.get("analysis")
        try:
            spec = catalog.get(name)
            result = spec.handler(**args)
            entry = {"tool": name, "ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001 — tool failures must not kill the graph
            entry = {"tool": name, "ok": False, "error": str(exc)}
        _publish(
            ToolExecuted(
                workflow_id=state.get("workflow_id", ""),
                tool=name,
                ok=entry["ok"],
            )
        )
        return {
            "tool_results": [entry],
            "step_count": state.get("step_count", 0) + 1,
            "consecutive_failures": (
                0 if entry["ok"] else state.get("consecutive_failures", 0) + 1
            ),
            "status": WorkflowStatus.ROUTING.value,
        }

    def notify_approval(state: AgentState) -> AgentState:
        """Record the approval request and alert a human. Runs exactly once
        per gate hit — the interrupt lives in await_approval so this node's
        side effects are not replayed on resume."""
        diffs = [
            r["result"]
            for r in state.get("tool_results", [])
            if r.get("ok") and r.get("tool") in {"draft_fix", "propose_edit"}
        ]
        analysis = state.get("analysis") or {}
        payload = {
            "workflow_id": state.get("workflow_id", ""),
            "action": "finalize_workflow",
            "issue": state.get("issue", {}),
            "summary": analysis.get("symptoms", ""),
            "diffs": diffs,
            "test_summary": "not run (sandbox arrives with test_verification)",
            "risk": (
                f"severity={analysis.get('severity', 'unknown')}, "
                f"area={analysis.get('affected_area', 'unknown')}"
            ),
        }
        if request_approval_hook:
            try:
                request_approval_hook(payload)
            except Exception:  # noqa: BLE001 — notification must not break the pause
                logger.exception(
                    "Approval request hook failed for %s", payload["workflow_id"]
                )
        _publish(
            WorkflowPaused(
                workflow_id=payload["workflow_id"], reason="awaiting_approval"
            )
        )
        return {
            "status": WorkflowStatus.AWAITING_APPROVAL.value,
            "pending_approval": payload,
            "decisions": [
                Decision(
                    node="notify_approval",
                    action="request_approval",
                    reasoning="Irreversible step ahead; human sign-off required.",
                ).to_dict()
            ],
        }

    def await_approval(state: AgentState) -> AgentState:
        """Pause here until a human decision resumes the graph (F-07)."""
        decision = interrupt(state.get("pending_approval", {}))
        approved = bool(decision.get("approved"))
        feedback = str(decision.get("feedback", ""))
        if approved:
            return {
                "approval_decision": "approved",
                "status": WorkflowStatus.ROUTING.value,
                "decisions": [
                    Decision(
                        node="await_approval",
                        action="approved",
                        reasoning=feedback or "Approved by human reviewer.",
                    ).to_dict()
                ],
            }
        return {
            "approval_decision": "rejected",
            "approval_feedback": feedback,
            "approval_retry_count": state.get("approval_retry_count", 0) + 1,
            "status": WorkflowStatus.ROUTING.value,
            "decisions": [
                Decision(
                    node="await_approval",
                    action="rejected",
                    reasoning=feedback or "Rejected by human reviewer.",
                ).to_dict()
            ],
        }

    def finalize(state: AgentState) -> AgentState:
        return {
            "status": WorkflowStatus.DONE.value,
            "decisions": [
                Decision(
                    node="finalize", action=FINISH, reasoning="Workflow complete."
                ).to_dict()
            ],
        }

    def escalate(state: AgentState) -> AgentState:
        return {
            "status": WorkflowStatus.ESCALATED.value,
            "decisions": [
                Decision(
                    node="escalate",
                    action=ESCALATE,
                    reasoning=state.get("error") or "Escalated to human review.",
                ).to_dict()
            ],
        }

    def _with_decision_logging(name: str, fn):
        """Emit every decision a node records as a structured JSON log line."""

        def wrapped(state: AgentState) -> AgentState:
            delta = fn(state)
            for decision in delta.get("decisions") or []:
                decision_logger.log(state.get("workflow_id", ""), decision)
            return delta

        wrapped.__name__ = name
        return wrapped

    return {
        name: _with_decision_logging(name, fn)
        for name, fn in {
            "analyze_issue": analyze_issue,
            "request_clarification": request_clarification,
            "route": route,
            "execute_tool": execute_tool,
            "notify_approval": notify_approval,
            "await_approval": await_approval,
            "finalize": finalize,
            "escalate": escalate,
        }.items()
    }
