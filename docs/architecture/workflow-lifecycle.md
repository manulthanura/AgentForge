# Workflow Lifecycle

One workflow = one GitHub issue. The LangGraph state machine
(`src/workflow_orchestration/infrastructure/langgraph/graph.py`):

```
START ──▶ analyze_issue ─┬─ insufficient_information ──▶ request_clarification ──▶ END
                         ├─ analysis failed ──▶ escalate ──▶ END
                         └─▶ route ─┬─ tool name ──▶ execute_tool ──▶ route   (loop)
                                    ├─ finish ──▶ notify_approval ──▶ await_approval
                                    │             (skips straight to finalize when
                                    │              REQUIRE_APPROVAL=false)
                                    └─ escalate ──▶ escalate ──▶ END

await_approval ─┬─ approved ──▶ finalize ──▶ END
                ├─ rejected, retries left ──▶ route          (feedback in context)
                └─ rejected > MAX_APPROVAL_RETRIES ──▶ escalate ──▶ END
```

## Statuses

`analyzing → routing → awaiting_clarification | awaiting_approval | done | escalated`
(`WorkflowStatus` in `workflow_orchestration/domain/models.py`; also
`awaiting_approval` re-entered after each rejection, `timed_out` reserved
for expired approvals).

## The router

`AgentRouter` (application layer) asks the LLM for the single best next
action given the issue, its analysis, prior decisions, tool results, step
budget, and any human feedback. It answers with strict JSON
(`{"action", "args", "reasoning"}`); anything unparseable or naming an
unknown tool degrades to `escalate`. Every decision — including the
reasoning — is appended to the state's decision log **and** emitted as a
structured JSON log line (see
[../features/observability.md](../features/observability.md)).

Guards evaluated before the LLM is consulted:

| Guard | Trigger | Outcome |
|-------|---------|---------|
| Step budget | `step_count >= MAX_AGENT_STEPS` (default 8) | escalate |
| Compound failure (R-09) | `MAX_CONSECUTIVE_FAILURES` failed tools in a row (default 3) | escalate |

## Pause and resume (F-07)

Pausing is two nodes on purpose:

1. **notify_approval** — persists the `ApprovalRequest`, notifies a human
   (Slack/email), publishes `WorkflowPaused`. Runs exactly once per gate.
2. **await_approval** — calls LangGraph's `interrupt(payload)`. The graph
   checkpoints and stops. When a node containing `interrupt()` resumes it
   is **re-executed from the top**, which is why the side effects live in
   the previous node — otherwise every resume would re-notify the reviewer.

Resume path: a signed Slack interaction hits
`HandleApprovalResponseUseCase`, which records the decision and calls
`ResumeWorkflowUseCase` → `engine.resume(Command(resume=decision))`. The
workflow continues from the exact checkpoint with its full pre-pause state —
hours or days later, across process restarts.

## Persistence

| Store | What | Where |
|-------|------|-------|
| LangGraph checkpoints | full state after every node (the resume source) | `checkpoints*` tables, managed by `PostgresSaver` |
| `workflows` table | queryable index: status, classification, timestamps | `migrations/0001_workflows.sql` |
| `approvals` table | one pending human decision per workflow | `migrations/0002_approvals.sql` |

Corrupted checkpoints are detected and skipped in favor of the last valid
one in history (R-08 — see
[../features/reliability.md](../features/reliability.md)).
