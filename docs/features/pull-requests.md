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

## Not yet implemented

The `finalize` node does not yet invoke this use case automatically — the
use case, adapter, and composition are in place and tested
(`tests/pull_request/`), but wiring PR creation into the post-approval
graph step (and adapting to branch-protection rules, C-02) is remaining
work.
