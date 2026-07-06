"""End-to-end state machine runs with an in-memory checkpointer."""

from __future__ import annotations

import json

from langgraph.checkpoint.memory import InMemorySaver

from shared_kernel.config.settings import Settings
from shared_kernel.events import EventBus, IssueAnalyzed, ToolExecuted
from workflow_orchestration.bootstrap import build_agent_graph

from tests.support.fakes import FailingProvider, FakeProvider

ANALYSIS_BUG = json.dumps(
    {
        "issue_type": "bug",
        "affected_area": "authentication",
        "symptoms": "login failure with special characters",
        "severity": "high",
        "reasoning": "Clear reproduction steps point at email validation.",
    }
)

ANALYSIS_VAGUE = json.dumps(
    {
        "issue_type": "insufficient_information",
        "affected_area": "unknown",
        "symptoms": "unspecified",
        "severity": "low",
        "reasoning": "No reproduction steps or symptoms given.",
    }
)


def _route(action, args=None, reasoning="next step"):
    return json.dumps({"action": action, "args": args or {}, "reasoning": reasoning})


def _initial(issue, workspace="."):
    return {
        "workflow_id": f"wf-{issue['number']}",
        "issue": issue,
        "workspace": workspace,
        "status": "analyzing",
        "step_count": 0,
    }


def _config(issue):
    return {"configurable": {"thread_id": f"wf-{issue['number']}"}}


def test_happy_path_runs_tools_then_finishes(sample_issue, tmp_path):
    (tmp_path / "login.py").write_text("email = raw\n", encoding="utf-8")
    provider = FakeProvider(
        responses=[
            ANALYSIS_BUG,
            _route("read_issue"),
            _route("search_code", {"query": "email"}),
            _route("finish", reasoning="Analysis and code context gathered."),
        ]
    )
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())
    final = graph.invoke(_initial(sample_issue, str(tmp_path)), _config(sample_issue))

    assert final["status"] == "done"
    assert final["classification"] == "bug"
    assert final["analysis"]["affected_area"] == "authentication"

    # Both tools executed successfully.
    tools_run = [(r["tool"], r["ok"]) for r in final["tool_results"]]
    assert tools_run == [("read_issue", True), ("search_code", True)]
    assert final["tool_results"][1]["result"]["matches"]  # found login.py

    # Decision transparency: every step logged with reasoning.
    nodes = [d["node"] for d in final["decisions"]]
    assert nodes == ["analyze_issue", "route", "route", "route", "finalize"]
    assert all("reasoning" in d for d in final["decisions"])


def test_vague_issue_requests_clarification_and_skips_tools(vague_issue):
    provider = FakeProvider(responses=[ANALYSIS_VAGUE])
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())
    final = graph.invoke(_initial(vague_issue), _config(vague_issue))

    assert final["status"] == "awaiting_clarification"
    assert final["classification"] == "insufficient_information"
    assert final.get("tool_results", []) == []
    # Only the analysis call hit the LLM — the router was never consulted.
    assert len(provider.calls) == 1


def test_step_budget_exhaustion_escalates(sample_issue, monkeypatch):
    monkeypatch.setenv("MAX_AGENT_STEPS", "2")
    provider = FakeProvider(
        responses=[ANALYSIS_BUG]
        + [_route("read_issue", reasoning="loop") for _ in range(10)]
    )
    graph = build_agent_graph(
        provider, settings=Settings(), checkpointer=InMemorySaver()
    )
    final = graph.invoke(_initial(sample_issue), _config(sample_issue))

    assert final["status"] == "escalated"
    assert len(final["tool_results"]) == 2  # stopped at the budget
    assert any(
        "budget exhausted" in d.get("reasoning", "").lower()
        for d in final["decisions"]
    )


def test_llm_outage_during_analysis_escalates(sample_issue):
    graph = build_agent_graph(FailingProvider(), checkpointer=InMemorySaver())
    final = graph.invoke(_initial(sample_issue), _config(sample_issue))
    assert final["status"] == "escalated"
    assert "analysis failed" in final["error"].lower()


def test_tool_failure_is_recorded_not_fatal(sample_issue):
    provider = FakeProvider(
        responses=[
            ANALYSIS_BUG,
            # Router asks for a tool with bad args -> handler raises TypeError.
            _route("propose_edit", {"bogus_arg": True}),
            _route("finish"),
        ]
    )
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())
    final = graph.invoke(_initial(sample_issue), _config(sample_issue))
    assert final["status"] == "done"
    assert final["tool_results"][0]["ok"] is False
    assert "error" in final["tool_results"][0]


def test_state_is_persisted_in_checkpointer(sample_issue):
    provider = FakeProvider(responses=[ANALYSIS_BUG, _route("finish")])
    graph = build_agent_graph(provider, checkpointer=InMemorySaver())
    config = _config(sample_issue)
    graph.invoke(_initial(sample_issue), config)

    # The checkpoint for this thread reflects the final state and can be
    # re-read later (resume-from-checkpoint foundation for Phase 3).
    snapshot = graph.get_state(config)
    assert snapshot.values["status"] == "done"
    assert snapshot.values["workflow_id"] == "wf-42"
    assert len(snapshot.values["decisions"]) >= 2


def test_concurrent_workflows_keep_independent_state(sample_issue, vague_issue):
    checkpointer = InMemorySaver()
    graph_a = build_agent_graph(
        FakeProvider(responses=[ANALYSIS_BUG, _route("finish")]),
        checkpointer=checkpointer,
    )
    graph_b = build_agent_graph(
        FakeProvider(responses=[ANALYSIS_VAGUE]), checkpointer=checkpointer
    )

    final_a = graph_a.invoke(_initial(sample_issue), _config(sample_issue))
    final_b = graph_b.invoke(_initial(vague_issue), _config(vague_issue))

    assert final_a["status"] == "done"
    assert final_b["status"] == "awaiting_clarification"
    assert graph_a.get_state(_config(sample_issue)).values["status"] == "done"
    assert (
        graph_b.get_state(_config(vague_issue)).values["status"]
        == "awaiting_clarification"
    )


def test_domain_events_published_during_run(sample_issue):
    bus = EventBus()
    analyzed: list[IssueAnalyzed] = []
    executed: list[ToolExecuted] = []
    bus.subscribe(IssueAnalyzed, analyzed.append)
    bus.subscribe(ToolExecuted, executed.append)

    provider = FakeProvider(
        responses=[ANALYSIS_BUG, _route("read_issue"), _route("finish")]
    )
    graph = build_agent_graph(provider, checkpointer=InMemorySaver(), event_bus=bus)
    graph.invoke(_initial(sample_issue), _config(sample_issue))

    assert [e.classification for e in analyzed] == ["bug"]
    assert [(e.tool, e.ok) for e in executed] == [("read_issue", True)]
