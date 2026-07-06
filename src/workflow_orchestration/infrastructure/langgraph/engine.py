"""WorkflowEngine port implementation backed by a compiled LangGraph."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from ...application.ports import WorkflowEngine
from ...domain.models import WorkflowStatus

logger = logging.getLogger(__name__)


class LangGraphWorkflowEngine(WorkflowEngine):
    def __init__(self, compiled_graph):
        self._graph = compiled_graph

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            # Surfaced in LangSmith traces for per-workflow filtering.
            "run_name": f"agentforge:{thread_id}",
            "metadata": {"workflow_id": thread_id},
            "tags": ["agentforge"],
        }

    def run(self, initial_state: dict[str, Any], thread_id: str) -> dict[str, Any]:
        return self._normalize(
            self._graph.invoke(initial_state, self._config(thread_id))
        )

    def resume(self, decision: dict[str, Any], thread_id: str) -> dict[str, Any]:
        """Continue a paused workflow from its checkpoint with a decision."""
        return self._normalize(
            self._graph.invoke(Command(resume=decision), self._config(thread_id))
        )

    def get_state(self, thread_id: str) -> dict[str, Any]:
        """Read the checkpointed state; on corruption, fall back to the last
        valid checkpoint in the thread's history (R-08)."""
        config = self._config(thread_id)
        values = dict(self._graph.get_state(config).values)
        if not values or self._is_valid_state(values):
            return values

        logger.warning(
            "Corrupted checkpoint for %s; searching history for the last "
            "valid checkpoint",
            thread_id,
        )
        for snapshot in self._graph.get_state_history(config):
            candidate = dict(snapshot.values)
            if candidate and self._is_valid_state(candidate):
                return candidate
        logger.error("No valid checkpoint found for %s", thread_id)
        return {}

    @staticmethod
    def _is_valid_state(values: dict[str, Any]) -> bool:
        status = values.get("status")
        if status is not None:
            try:
                WorkflowStatus(status)
            except ValueError:
                return False
        for key in ("decisions", "tool_results"):
            if key in values and not isinstance(values[key], list):
                return False
        if "issue" in values and not isinstance(values["issue"], dict):
            return False
        return True

    @staticmethod
    def _normalize(result: dict[str, Any]) -> dict[str, Any]:
        # Interrupt markers aren't part of workflow state (and don't
        # serialize); the reviewer payload already lives in pending_approval.
        result.pop("__interrupt__", None)
        return result
