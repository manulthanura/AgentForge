"""LangGraph state machine wiring.

analyze_issue ─┬─ insufficient_information → request_clarification → END
               └─ otherwise → route ─┬─ tool name → execute_tool → route (loop)
                                     ├─ finish → notify_approval → await_approval
                                     │            (or straight to finalize when
                                     │             approval is not required)
                                     └─ escalate → escalate → END

await_approval interrupts the graph (checkpointed pause). On resume:
approved → finalize; rejected → route (with feedback) until the retry
budget runs out, then escalate.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from issue_intake.application.analyze_issue import AnalyzeIssueUseCase
from issue_intake.domain.models import IssueType
from shared_kernel.config.settings import Settings, get_settings
from shared_kernel.events import EventBus

from ...application.routing import ESCALATE, FINISH, AgentRouter
from ...application.tools import ToolCatalog
from ...domain.models import WorkflowStatus
from .nodes import ApprovalHook, make_nodes
from .state import AgentState


def _after_analysis(state: AgentState) -> str:
    if state.get("status") == WorkflowStatus.ESCALATED.value:
        return "escalate"
    if state.get("classification") == IssueType.INSUFFICIENT_INFORMATION.value:
        return "request_clarification"
    return "route"


def build_graph(
    analyze_issue_uc: AnalyzeIssueUseCase,
    router: AgentRouter,
    catalog: ToolCatalog,
    settings: Settings | None = None,
    checkpointer=None,
    event_bus: EventBus | None = None,
    request_approval_hook: ApprovalHook | None = None,
):
    """Compile the agent state machine from its collaborators."""
    settings = settings or get_settings()
    nodes = make_nodes(
        analyze_issue_uc,
        router,
        catalog,
        settings,
        event_bus,
        request_approval_hook,
    )

    def _after_route(state: AgentState) -> str:
        action = state.get("next_action", ESCALATE)
        if action == FINISH:
            return "notify_approval" if settings.require_approval else "finalize"
        if action == ESCALATE:
            return "escalate"
        return "execute_tool"

    def _after_approval(state: AgentState) -> str:
        if state.get("approval_decision") == "approved":
            return "finalize"
        if state.get("approval_retry_count", 0) > settings.max_approval_retries:
            return "escalate"
        return "route"

    graph = StateGraph(AgentState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "analyze_issue")
    graph.add_conditional_edges(
        "analyze_issue",
        _after_analysis,
        {
            "escalate": "escalate",
            "request_clarification": "request_clarification",
            "route": "route",
        },
    )
    graph.add_conditional_edges(
        "route",
        _after_route,
        {
            "finalize": "finalize",
            "notify_approval": "notify_approval",
            "escalate": "escalate",
            "execute_tool": "execute_tool",
        },
    )
    graph.add_edge("execute_tool", "route")
    graph.add_edge("notify_approval", "await_approval")
    graph.add_conditional_edges(
        "await_approval",
        _after_approval,
        {"finalize": "finalize", "route": "route", "escalate": "escalate"},
    )
    graph.add_edge("request_clarification", END)
    graph.add_edge("finalize", END)
    graph.add_edge("escalate", END)

    return graph.compile(checkpointer=checkpointer)
