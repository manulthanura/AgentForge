# Issue Intake

Turning a raw GitHub issue into a structured, classified analysis the agent
can act on (F-01) — and refusing to act when there is nothing to act on.

## The model

`Issue` (number, title, body, labels) and `IssueAnalysis` are frozen
dataclasses in `src/issue_intake/domain/models.py` — pure, no SDK imports.
An analysis carries:

| Field | Values |
|-------|--------|
| `issue_type` | `bug` \| `feature_request` \| `question` \| `insufficient_information` \| `unknown` |
| `affected_area` | subsystem name, or `unknown` |
| `symptoms` | short summary |
| `severity` | `low` \| `medium` \| `high` |
| `reasoning` | why the classifier decided this |

## Classification

`AnalyzeIssueUseCase` sends the issue (title, body, labels) to the LLM port
with a strict-JSON system prompt and builds an `IssueAnalysis` from the
reply. The parsing is defensive by design — LLM output is untrusted:

- an unrecognized `issue_type` degrades to `unknown`, never raises;
- an unrecognized `severity` degrades to `medium`;
- missing fields get safe defaults (`affected_area="unknown"`, empty strings).

Provider failures (`LLMError` and friends) propagate to the workflow's
`analyze_issue` node, which escalates the workflow rather than guessing.

## The vague-issue gate

If the issue lacks enough information to act on ("it doesn't work" /
"please fix"), the classifier returns `insufficient_information`. The
workflow then takes the `request_clarification` branch and **stops** with
status `awaiting_clarification` — it never proceeds to code search on a
guess (see [../architecture/workflow-lifecycle.md](../architecture/workflow-lifecycle.md)).
`IssueAnalysis.needs_clarification` is the single source of truth for this
branch.

## Reading real issues (GitHub)

`GitHubIssueReader` (infrastructure) implements the `IssueReader` port with
PyGithub. It is enabled only when both `GITHUB_TOKEN` and `GITHUB_REPO` are
set — otherwise workflows run on the issue payload delivered by the webhook
alone, which is all the demo and tests need.

Transient GitHub failures (429/500/502/503/504) back off and retry with
`Retry-After` respected (R-03, via `shared_kernel/resilience`); anything
else raises a typed `IssueReadError`. See
[reliability.md](reliability.md) for the retry policy.

## Not yet implemented

Posting the clarification questions back to the GitHub issue as a comment,
and duplicate detection (similarity scoring against previously processed
issues, F-08). The workflow-side pause (`awaiting_clarification`) is in
place for both.
