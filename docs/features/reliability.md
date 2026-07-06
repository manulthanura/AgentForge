# Reliability

What happens when things go wrong — the Phase 4 implementation of the
reliability lens (R-01…R-09). Run just these tests with
`uv run pytest tests/ -k reliability`.

## Retry with exponential backoff (R-02, R-03)

Core: `shared_kernel/resilience/retry.py` — `RetryPolicy` (3 retries,
delays 2s → 4s → 8s, configurable via `RETRY_MAX_ATTEMPTS` /
`RETRY_BASE_DELAY`) and `retry_call` with an injectable `sleep` (tests
never actually wait). A server-provided `Retry-After` always overrides the
computed backoff.

**LLM calls** — adapters classify failures (see
[llm-providers.md](llm-providers.md)); `RetryingLLMProvider` retries only
the transient class:

```
503, 503, success  →  sleeps [2.0, 4.0], caller sees success
429 retry-after: 7 →  sleeps [7.0]
sustained outage   →  sleeps [2.0, 4.0, 8.0], then the error surfaces and
                      the workflow escalates cleanly with the reason logged
400 / refusal      →  no retry, immediate error
```

**GitHub calls** — `retrying_github_call` retries only 429/500/502/503/504,
honoring `Retry-After`; 404s and validation errors fail immediately. Wired
into `GitHubIssueReader` and `GitHubPRClient` (read-side calls and
`create_pull`; branch/commit writes are not blind-retried).

## Graceful degradation (R-09)

`FallbackCodeSearcher`: tree-sitter primary → filesystem fallback on any
exception. If both engines fail, the failure is recorded as a tool result —
and the workflow tracks `consecutive_failures` (reset on every success).
At `MAX_CONSECUTIVE_FAILURES` (3) the router escalates with a
"compound failure" decision instead of retrying forever.

## Corrupted checkpoint handling (R-08)

Two layers:

- **Engine** (`LangGraphWorkflowEngine.get_state`): validates the checkpoint
  (status parses as `WorkflowStatus`, decisions/tool_results are lists,
  issue is a dict). On corruption it walks `get_state_history` and returns
  the **last valid checkpoint**; only if none exists does it report empty.
- **Index repo** (`PostgresWorkflowRepository`): a row failing validation
  raises a typed `CorruptedWorkflowStateError` on `get()`; `list()` skips
  bad rows (with logging) so one corrupted workflow can't blind the
  dashboard.

## Failure containment elsewhere

| Failure | Behavior |
|---------|----------|
| Tool raises (bad args, broken adapter) | recorded as a failed tool result; workflow keeps routing |
| Router returns garbage / unknown action | degrades to `escalate`, never crashes |
| Notification delivery fails | logged; the approval pause proceeds regardless |
| Event handler raises | swallowed and logged; workflow unaffected |
| Runaway loop | step budget (`MAX_AGENT_STEPS`, 8) escalates |
| Approval never answered | reminder at 48h, timed out at 72h; checkpoint stays resumable (R-07) |

## Not yet implemented

Scheduled background retry after exhaustion ("retry in 30 minutes"),
GitHub-comment posting on timeout, and the Docker-sandbox crash recovery
(R-04/R-05 process-restart resume is inherent to Postgres checkpointing;
the sandbox itself arrives with `test_verification`).
