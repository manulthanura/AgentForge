"""Workflow-level reliability: outage recovery, compound-failure escalation,
and structured decision logging — all through the real state machine."""

from __future__ import annotations

import json
import logging

from langgraph.checkpoint.memory import InMemorySaver

from shared_kernel.config.settings import Settings
from shared_kernel.llm import LLMUnavailableError, RetryingLLMProvider
from workflow_orchestration.bootstrap import build_agent_graph

from tests.code_intelligence.unit.test_reliability_fallback import BrokenSearcher
from tests.support.fakes import FlakyProvider

ANALYSIS_BUG = json.dumps(
    {
        "issue_type": "bug",
        "affected_area": "authentication",
        "symptoms": "login failure",
        "severity": "high",
        "reasoning": "repro steps present",
    }
)


def _route(action, args=None, reasoning="next"):
    return json.dumps({"action": action, "args": args or {}, "reasoning": reasoning})


def _initial(issue):
    return {
        "workflow_id": f"wf-{issue['number']}",
        "issue": issue,
        "workspace": ".",
        "status": "analyzing",
        "step_count": 0,
    }


def _config(issue):
    return {"configurable": {"thread_id": f"wf-{issue['number']}"}}


def test_llm_outage_during_analysis_backs_off_and_recovers(sample_issue):
    """R-02: mock 503s during analysis; backoff kicks in, workflow completes."""
    sleeps: list[float] = []
    flaky = FlakyProvider(
        failures=[
            LLMUnavailableError("503 service unavailable"),
            LLMUnavailableError("503 service unavailable"),
        ],
        responses=[ANALYSIS_BUG, _route("finish")],
    )
    provider = RetryingLLMProvider(flaky, sleep=sleeps.append)
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())

    final = graph.invoke(_initial(sample_issue), _config(sample_issue))

    assert final["status"] == "done"  # recovered, not escalated
    assert sleeps == [2.0, 4.0]  # exponential backoff between the 503s
    assert final["classification"] == "bug"


def test_llm_outage_beyond_retry_budget_escalates_cleanly(sample_issue):
    sleeps: list[float] = []
    flaky = FlakyProvider(
        failures=[LLMUnavailableError("503") for _ in range(10)]
    )
    provider = RetryingLLMProvider(flaky, sleep=sleeps.append)
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())

    final = graph.invoke(_initial(sample_issue), _config(sample_issue))

    assert final["status"] == "escalated"
    assert sleeps == [2.0, 4.0, 8.0]  # full backoff before giving up
    assert "analysis failed" in final["error"].lower()


def test_compound_tool_failures_escalate_after_cap(sample_issue, monkeypatch):
    """R-09: search fails repeatedly (both engines down) -> escalate at 3."""
    monkeypatch.setenv("MAX_CONSECUTIVE_FAILURES", "3")
    provider = FlakyProvider(
        failures=[],
        responses=[ANALYSIS_BUG]
        + [_route("search_code", {"query": "auth"}) for _ in range(10)],
    )
    graph = build_agent_graph(
        provider,
        settings=Settings(),
        checkpointer=InMemorySaver(),
        searcher=BrokenSearcher(),  # every search raises
    )

    final = graph.invoke(_initial(sample_issue), _config(sample_issue))

    assert final["status"] == "escalated"
    failures = [r for r in final["tool_results"] if not r["ok"]]
    assert len(failures) == 3  # capped, not infinite
    assert any(
        "compound failure" in d.get("reasoning", "").lower()
        for d in final["decisions"]
    )


def test_successful_tool_resets_the_failure_counter(sample_issue, tmp_path):
    (tmp_path / "login.py").write_text("email = raw\n", encoding="utf-8")
    provider = FlakyProvider(
        failures=[],
        responses=[
            ANALYSIS_BUG,
            _route("propose_edit", {"bogus": True}),  # fails (bad args)
            _route("search_code", {"query": "email"}),  # succeeds -> reset
            _route("propose_edit", {"bogus": True}),  # fails again
            _route("finish"),
        ],
    )
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())
    initial = _initial(sample_issue) | {"workspace": str(tmp_path)}

    final = graph.invoke(initial, _config(sample_issue))

    assert final["status"] == "done"  # never hit the compound cap
    assert final["consecutive_failures"] == 1  # last failure, after a reset


def test_every_decision_is_logged_as_structured_json(sample_issue, caplog):
    provider = FlakyProvider(failures=[], responses=[ANALYSIS_BUG, _route("finish")])
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())

    with caplog.at_level(logging.INFO, logger="agentforge.decisions"):
        graph.invoke(_initial(sample_issue), _config(sample_issue))

    records = [json.loads(r.message) for r in caplog.records]
    assert records, "expected structured decision log lines"
    assert all(r["workflow_id"] == "wf-42" for r in records)
    # The router's choice is logged with its reasoning (why this tool).
    route_entries = [r for r in records if r["node"] == "route"]
    assert route_entries and route_entries[0]["reasoning"]
    assert {"node", "action", "reasoning", "at"} <= set(records[0])
