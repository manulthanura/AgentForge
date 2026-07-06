"""Agent router: decision parsing, validation, and failure fallbacks."""

from __future__ import annotations

import json

from code_intelligence.application.search_relevant_code import (
    SearchRelevantCodeUseCase,
)
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)
from fix_generation.application.propose_fix import ProposeFixUseCase
from workflow_orchestration.application.routing import ESCALATE, AgentRouter
from workflow_orchestration.application.tools import build_default_catalog

from tests.support.fakes import FailingProvider, FakeProvider


def _catalog():
    return build_default_catalog(
        search_code=SearchRelevantCodeUseCase(FilesystemCodeSearcher()),
        propose_fix=ProposeFixUseCase(),
    )


def _router(responses=None):
    provider = FakeProvider(responses=responses)
    return AgentRouter(provider, _catalog()), provider


def test_valid_tool_decision():
    router, _ = _router(
        [
            json.dumps(
                {
                    "action": "search_code",
                    "args": {"query": "email validation"},
                    "reasoning": "Need to find the auth code first.",
                }
            )
        ]
    )
    decision = router.decide({"issue": {"title": "bug"}})
    assert decision.action == "search_code"
    assert decision.args == {"query": "email validation"}
    assert "auth code" in decision.reasoning


def test_finish_and_escalate_are_valid_actions():
    router, _ = _router(['{"action": "finish", "args": {}, "reasoning": "done"}'])
    assert router.decide({}).action == "finish"


def test_invalid_action_falls_back_to_escalate():
    router, _ = _router(['{"action": "rm_rf_slash", "args": {}, "reasoning": "!"}'])
    decision = router.decide({})
    assert decision.action == ESCALATE
    assert "invalid action" in decision.reasoning


def test_malformed_json_falls_back_to_escalate():
    router, _ = _router(["this is not json at all"])
    assert router.decide({}).action == ESCALATE


def test_provider_outage_falls_back_to_escalate():
    router = AgentRouter(FailingProvider(), _catalog())
    decision = router.decide({})
    assert decision.action == ESCALATE
    assert "failed" in decision.reasoning.lower()


def test_router_prompt_includes_tools_and_history():
    router, provider = _router(['{"action": "finish", "args": {}, "reasoning": ""}'])
    state = {
        "issue": {"title": "login bug"},
        "decisions": [{"action": "read_issue", "reasoning": "start"}],
        "tool_results": [{"tool": "read_issue", "ok": True}],
    }
    router.decide(state)
    call = provider.calls[0]
    assert "search_code" in call["system"]  # tool catalog present
    assert "login bug" in call["messages"][0]["content"]  # state serialized
    assert "read_issue" in call["messages"][0]["content"]  # history serialized
