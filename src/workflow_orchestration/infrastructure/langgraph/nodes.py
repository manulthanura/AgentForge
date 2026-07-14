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
from pull_request.application.create_pull_request import CreatePullRequestUseCase
from pull_request.application.ports import PullRequestError
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

# Called with (issue_number, comment_body) whenever a workflow reaches a
# terminal or human-actionable state, so the outcome shows up on the GitHub
# issue itself instead of requiring status polling. The bootstrap wires
# IssueCommenter.add_comment in here.
CommentHook = Callable[[int, str], Any]


def make_nodes(
    analyze_issue_uc: AnalyzeIssueUseCase,
    router: AgentRouter,
    catalog: ToolCatalog,
    settings: Settings,
    event_bus: EventBus | None = None,
    request_approval_hook: ApprovalHook | None = None,
    decision_logger: DecisionLogger | None = None,
    create_pull_request_uc: CreatePullRequestUseCase | None = None,
    comment_hook: CommentHook | None = None,
) -> dict[str, Any]:
    """Build the node callables bound to their collaborators."""
    decision_logger = decision_logger or DecisionLogger()

    def _publish(event) -> None:
        if event_bus:
            event_bus.publish(event)

    def _post_comment(state: AgentState, body: str) -> None:
        if not comment_hook:
            return
        number = int((state.get("issue") or {}).get("number", 0))
        if not number:
            return
        try:
            comment_hook(number, body)
            logger.info("Posted comment on issue #%s", number)
        except Exception:  # noqa: BLE001 — a failed comment must not break the workflow
            logger.exception("Comment hook failed for issue #%s", number)

    def _collect_diffs(state: AgentState) -> list[dict[str, Any]]:
        return [
            r["result"]
            for r in state.get("tool_results", [])
            if r.get("ok") and r.get("tool") in {"draft_fix", "propose_edit"}
        ]

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
        _post_comment(
            state,
            "This issue needs more detail before AgentForge can work on it. "
            "Could you add:\n"
            "- Steps to reproduce the issue\n"
            "- Expected vs actual behavior\n"
            "- Environment details",
        )
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
        diffs = _collect_diffs(state)
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
        if create_pull_request_uc is None:
            _post_comment(
                state,
                "AgentForge finished analyzing this issue. Pull-request "
                "creation isn't enabled for this deployment, so no PR was "
                "opened.",
            )
            return {
                "status": WorkflowStatus.DONE.value,
                "decisions": [
                    Decision(
                        node="finalize", action=FINISH, reasoning="Workflow complete."
                    ).to_dict()
                ],
            }

        diffs = _collect_diffs(state)
        changes = {
            d["path"]: d["updated"]
            for d in diffs
            if d.get("path") and d.get("updated")
        }
        if not changes:
            _post_comment(
                state,
                "AgentForge analyzed this issue but did not produce a code "
                "change to open a pull request for.",
            )
            return {
                "status": WorkflowStatus.DONE.value,
                "decisions": [
                    Decision(
                        node="finalize",
                        action=FINISH,
                        reasoning="Workflow complete; no file changes to open a PR for.",
                    ).to_dict()
                ],
            }

        try:
            pr = create_pull_request_uc.execute(
                issue=state.get("issue", {}),
                analysis=state.get("analysis"),
                diffs=diffs,
                changes=changes,
            )
        except PullRequestError as exc:
            _post_comment(
                state,
                "AgentForge drafted a fix for this issue, but opening the "
                f"pull request failed: {exc}",
            )
            return {
                "status": WorkflowStatus.DONE.value,
                "pull_request": {"error": str(exc)},
                "decisions": [
                    Decision(
                        node="finalize",
                        action="pr_failed",
                        reasoning=str(exc),
                    ).to_dict()
                ],
            }
        _post_comment(
            state, f"AgentForge opened a pull request with a proposed fix: {pr.url}"
        )
        return {
            "status": WorkflowStatus.DONE.value,
            "pull_request": {
                "number": pr.number,
                "url": pr.url,
                "branch": pr.branch,
            },
            "decisions": [
                Decision(
                    node="finalize",
                    action="pr_opened",
                    reasoning=f"Opened PR #{pr.number}: {pr.url}",
                ).to_dict()
            ],
        }

    def escalate(state: AgentState) -> AgentState:
        reasoning = state.get("error") or "Escalated to human review."
        _post_comment(
            state,
            "AgentForge could not complete this issue automatically and is "
            f"escalating for human review.\n\nReason: {reasoning}",
        )
        return {
            "status": WorkflowStatus.ESCALATED.value,
            "decisions": [
                Decision(
                    node="escalate",
                    action=ESCALATE,
                    reasoning=reasoning,
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
