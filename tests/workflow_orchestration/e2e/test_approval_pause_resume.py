"""Approval gate pause/resume against the real graph (F-07), in memory.

Covers the approval.feature scenarios at the state-machine level; the HTTP
end-to-end variant lives in test_http_approval_flow.py.
"""

from __future__ import annotations

import json

from langgraph.checkpoint.memory import InMemorySaver

from shared_kernel.config.settings import Settings
from workflow_orchestration.application.resume_workflow import ResumeWorkflowUseCase
from workflow_orchestration.application.run_workflow import RunWorkflowUseCase
from workflow_orchestration.bootstrap import build_workflow_engine

from tests.support.fakes import FakeProvider

ANALYSIS_BUG = json.dumps(
    {
        "issue_type": "bug",
        "affected_area": "authentication",
        "symptoms": "login failure with special characters",
        "severity": "high",
        "reasoning": "Reproduction steps included.",
    }
)


def _route(action, args=None, reasoning="next"):
    return json.dumps({"action": action, "args": args or {}, "reasoning": reasoning})


def _gated_engine(provider, monkeypatch, hook=None, max_retries=3):
    monkeypatch.setenv("REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("MAX_APPROVAL_RETRIES", str(max_retries))
    return build_workflow_engine(
        provider,
        settings=Settings(),
        checkpointer=InMemorySaver(),
        request_approval_hook=hook,
    )


def test_workflow_pauses_at_gate_with_full_context(
    monkeypatch, sample_issue
):
    hook_payloads = []
    provider = FakeProvider(responses=[ANALYSIS_BUG, _route("finish")])
    engine = _gated_engine(provider, monkeypatch, hook=hook_payloads.append)
    run = RunWorkflowUseCase(engine)

    paused = run.execute("wf-42", sample_issue)

    assert paused["status"] == "awaiting_approval"
    assert paused["pending_approval"]["workflow_id"] == "wf-42"
    # The approval hook received the reviewer payload exactly once.
    assert [p["workflow_id"] for p in hook_payloads] == ["wf-42"]
    assert "severity=high" in hook_payloads[0]["risk"]
    # Checkpoint retains the paused state.
    assert engine.get_state("wf-42")["status"] == "awaiting_approval"


def test_resume_after_approval_completes_with_full_state(
    monkeypatch, sample_issue
):
    provider = FakeProvider(responses=[ANALYSIS_BUG, _route("finish")])
    engine = _gated_engine(provider, monkeypatch)
    RunWorkflowUseCase(engine).execute("wf-42", sample_issue)

    # Hours later, the approval event fires (F-07).
    final = ResumeWorkflowUseCase(engine).execute("wf-42", {"approved": True})

    assert final["status"] == "done"
    # Full pre-pause state survived: analysis, decision log, issue.
    assert final["analysis"]["affected_area"] == "authentication"
    assert final["issue"]["number"] == 42
    nodes = [d["node"] for d in final["decisions"]]
    assert nodes == [
        "analyze_issue",
        "route",
        "notify_approval",
        "await_approval",
        "finalize",
    ]
    approval_entry = final["decisions"][3]
    assert approval_entry["action"] == "approved"


def test_rejection_feedback_reaches_router_then_second_approval_wins(
    monkeypatch, sample_issue
):
    provider = FakeProvider(
        responses=[
            ANALYSIS_BUG,
            _route("finish", reasoning="first attempt"),
            # After rejection the router is consulted again.
            _route("finish", reasoning="second attempt per feedback"),
        ]
    )
    engine = _gated_engine(provider, monkeypatch)
    RunWorkflowUseCase(engine).execute("wf-42", sample_issue)
    resume = ResumeWorkflowUseCase(engine)

    paused_again = resume.execute(
        "wf-42", {"approved": False, "feedback": "Try a different approach"}
    )
    assert paused_again["status"] == "awaiting_approval"
    assert paused_again["approval_retry_count"] == 1
    # The router's second consultation saw the human feedback.
    second_router_prompt = provider.calls[-1]["messages"][0]["content"]
    assert "Try a different approach" in second_router_prompt

    final = resume.execute("wf-42", {"approved": True})
    assert final["status"] == "done"


def test_rejections_beyond_retry_budget_escalate(monkeypatch, sample_issue):
    provider = FakeProvider(
        responses=[ANALYSIS_BUG] + [_route("finish") for _ in range(5)]
    )
    engine = _gated_engine(provider, monkeypatch, max_retries=1)
    RunWorkflowUseCase(engine).execute("wf-42", sample_issue)
    resume = ResumeWorkflowUseCase(engine)

    first = resume.execute("wf-42", {"approved": False, "feedback": "no"})
    assert first["status"] == "awaiting_approval"

    final = resume.execute("wf-42", {"approved": False, "feedback": "still no"})
    assert final["status"] == "escalated"
    assert final["approval_retry_count"] == 2


def test_concurrent_workflows_pause_and_resume_independently(
    monkeypatch, sample_issue, vague_issue
):
    checkpointer = InMemorySaver()
    monkeypatch.setenv("REQUIRE_APPROVAL", "true")
    settings = Settings()

    issue_b = dict(sample_issue, number=43, title="Other bug")
    engine_a = build_workflow_engine(
        FakeProvider(responses=[ANALYSIS_BUG, _route("finish")]),
        settings=settings,
        checkpointer=checkpointer,
    )
    engine_b = build_workflow_engine(
        FakeProvider(responses=[ANALYSIS_BUG, _route("finish")]),
        settings=settings,
        checkpointer=checkpointer,
    )
    RunWorkflowUseCase(engine_a).execute("wf-42", sample_issue)
    RunWorkflowUseCase(engine_b).execute("wf-43", issue_b)

    # Approve only wf-42; wf-43 must stay paused with independent state.
    final_a = ResumeWorkflowUseCase(engine_a).execute("wf-42", {"approved": True})
    assert final_a["status"] == "done"
    assert engine_b.get_state("wf-43")["status"] == "awaiting_approval"
    assert engine_b.get_state("wf-43")["issue"]["number"] == 43
