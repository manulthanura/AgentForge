# Pull Requests

Opening a well-formed PR for an approved fix (F-05). The PR body must stand
alone: a reviewer should not need to open the issue to understand the
change (U-05).

## What gets created

`CreatePullRequestUseCase` builds a `PullRequestDraft` from the workflow's
accumulated state:

| Element | Value |
|---------|-------|
| Title | `Fix #<issue>: <issue title>` |
| Branch | `agentforge/issue-<issue>` (from `base`, default `main`) |
| Body | `Closes #N` + summary from the issue analysis (symptoms, severity, area, reasoning) + every proposed diff in fenced ```diff blocks + test results + an "opened by AgentForge after human approval" footer |

## The GitHub adapter

`GitHubPRClient` (infrastructure) implements the `PullRequestGateway` port
with PyGithub:

1. create the branch ref from the base branch's head;
2. commit each changed file (`create_file`, or `update_file` when it
   already exists);
3. open the pull request.

Every GitHub interaction goes through `retrying_github_call` — 429/5xx
back off honoring `Retry-After` (R-03); branch/commit writes are **not**
blind-retried on other errors. Failures raise a typed `PullRequestError`
carrying the issue and repo context.

## Enablement and gating

- Composed by `src/bootstrap.py` only when `GITHUB_TOKEN` **and**
  `GITHUB_REPO` are set — without credentials the capability is simply
  absent (`Application.create_pull_request` is `None`).
- PR creation is the canonical irreversible action: it sits **after** the
  approval gate. Nothing reaches this context until a human has approved
  the diffs (see [human-in-the-loop.md](human-in-the-loop.md)).

## Wiring into the graph

The `finalize` node (`workflow_orchestration/infrastructure/langgraph/nodes.py`)
invokes `CreatePullRequestUseCase` automatically once the workflow reaches
that node, provided both:

- a gateway was composed (`GITHUB_TOKEN` + `GITHUB_REPO` set), and
- at least one `draft_fix`/`propose_edit` tool call produced file content
  (collected as `path -> updated content` from `tool_results`).

If either is missing, `finalize` just marks the workflow `done` — the
prior, PR-less behavior. Only `Diff.updated` (the full proposed file
content, not the diff text) is committed; the diff text is used for the PR
body only.

The result is written to `pull_request` in workflow state and surfaced by
`GET /workflows/{id}`:

- success: `{"number": ..., "url": ..., "branch": ...}`
- `PullRequestError` (e.g. branch-protection rejection): `{"error": "..."}`
  — the workflow still finishes as `done`; the PR failure is a separate,
  inspectable signal rather than an escalation.

Tests: `tests/workflow_orchestration/e2e/test_agent_graph.py`
(`test_finalize_opens_pull_request_when_wired`,
`test_finalize_without_pull_request_wiring_just_marks_done`,
`test_finalize_records_pr_failure_without_crashing_workflow`).

Adapting to branch-protection rules beyond what PyGithub surfaces (C-02)
remains future work.
