# ADR-006: Approval Gate via `interrupt()` Split Across Two Nodes

**Status**: accepted

## Context

Workflows must pause before irreversible actions and resume — possibly days
later — with full state (F-07). LangGraph re-executes a node from the top
when resuming through an `interrupt()` inside it, so any side effects in
that node would run again on every resume.

## Decision

Split the gate into two nodes:

1. `notify_approval` — persists the `ApprovalRequest`, sends the reviewer
   notification, publishes `WorkflowPaused`. Executes exactly once.
2. `await_approval` — contains only `decision = interrupt(payload)` plus
   pure state updates derived from the decision.

Resume enters through `ResumeWorkflowUseCase`, which implements the
approval context's `WorkflowResumer` port — the approval context never
imports orchestration internals.

## Trade-offs

One extra node and edge per gate. In exchange: no duplicate notifications
on resume, and rejection loops (feedback → router → new attempt → new gate)
fall out of the graph topology instead of bespoke state juggling.
