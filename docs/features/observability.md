# Observability

Two independent channels: LangSmith traces for deep inspection, structured
JSON decision logs for anything that can read a log line.

## LangSmith tracing

Enable by setting both:

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your LangSmith key>
LANGCHAIN_PROJECT=agentforge   # optional, this is the default
```

`init_tracing` (called from the composition root) turns tracing on only
when the key is actually present — a half-configured setup is
**hard-disabled** rather than left to spam auth errors on every run. Once
on, LangGraph traces every node execution natively (inputs/outputs,
latency, token usage). Each workflow run is stamped with
`run_name=agentforge:<workflow_id>`, a `workflow_id` metadata field, and an
`agentforge` tag, so a single workflow's whole story is one filter away.

## Structured decision logging

Every decision any node records — the router's tool choice and its
reasoning, analysis classification, approval outcomes, escalations — is
emitted as one JSON line on the `agentforge.decisions` logger:

```json
{"workflow_id": "issue-42", "node": "route", "action": "search_code",
 "reasoning": "Need to find the auth code first.",
 "args": {"query": "email validation"}, "at": "2026-07-04T12:00:00+00:00"}
```

This answers "why did the agent choose this tool?" (the Phase 4 decision
transparency requirement) without any external service: pipe it to your log
stack, or `grep agentforge.decisions`. The same decisions are also
persisted in workflow state (`decisions` list) and returned by
`GET /workflows/{id}`.

## Domain events

The in-process bus (`shared_kernel/events`) publishes `IssueAnalyzed`,
`ToolExecuted`, `WorkflowPaused`, `WorkflowFinished`, `WorkflowEscalated` —
subscribe for metrics or side channels; handler failures never propagate.

## Health

`GET /healthz` reports liveness plus which LLM provider is wired:
`{"ok": true, "provider": "anthropic"}`.
