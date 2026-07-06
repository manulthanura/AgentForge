"""Agent router: decides which tool to run next (or to finish/escalate).

The router talks to the provider-agnostic LLM port only. Every decision is
returned with reasoning so it can be logged for transparency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from shared_kernel.llm import LLMError, LLMProvider

from .tools import ToolCatalog

# Terminal actions the router may choose in addition to tool names.
FINISH = "finish"
ESCALATE = "escalate"


@dataclass
class RouterDecision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


SYSTEM_PROMPT = """\
You are the routing brain of AgentForge, an autonomous agent that resolves
GitHub issues. Given the issue, its analysis, and the work done so far,
choose the single best next action.

Available tools:
{tools}

Special actions:
- {finish}: the workflow has gathered enough to hand off (analysis complete, \
relevant code identified, and a fix proposed when appropriate).
- {escalate}: the agent cannot make progress and a human must take over.

Rules:
- Do not repeat a tool call that already succeeded with the same arguments.
- Prefer read_issue first, then search_code, then propose_edit, then {finish}.
- Respond with JSON: {{"action": "<name>", "args": {{...}}, "reasoning": "<why>"}}
"""


class AgentRouter:
    def __init__(self, provider: LLMProvider, catalog: ToolCatalog):
        self.provider = provider
        self.catalog = catalog

    def _valid_actions(self) -> set[str]:
        return set(self.catalog.names()) | {FINISH, ESCALATE}

    def decide(self, state: dict[str, Any]) -> RouterDecision:
        system = SYSTEM_PROMPT.format(
            tools=self.catalog.describe(), finish=FINISH, escalate=ESCALATE
        )
        context = {
            "issue": state.get("issue", {}),
            "analysis": state.get("analysis"),
            "decisions_so_far": [
                {"action": d.get("action"), "reasoning": d.get("reasoning")}
                for d in state.get("decisions", [])
            ],
            "tool_results_so_far": state.get("tool_results", []),
            "steps_used": state.get("step_count", 0),
            # Set when a human rejected the previous attempt — treat as the
            # highest-priority instruction for the next action.
            "human_feedback": state.get("approval_feedback", ""),
        }
        user = (
            "Current workflow state:\n"
            + json.dumps(context, default=str)[:12000]
            + "\nChoose the next action."
        )
        try:
            payload = self.provider.complete_json(
                [{"role": "user", "content": user}], system=system
            )
        except (LLMError, ValueError) as exc:
            return RouterDecision(
                action=ESCALATE,
                reasoning=f"Router LLM call failed: {exc}",
            )

        action = str(payload.get("action", "")).strip()
        args = payload.get("args") or {}
        reasoning = str(payload.get("reasoning", ""))
        if action not in self._valid_actions() or not isinstance(args, dict):
            return RouterDecision(
                action=ESCALATE,
                reasoning=(
                    f"Router returned invalid action {action!r}; "
                    f"raw reasoning: {reasoning!r}"
                ),
            )
        return RouterDecision(action=action, args=args, reasoning=reasoning)
