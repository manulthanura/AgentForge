# Fix Generation

Drafting fixes as **reviewable unified diffs** (F-03). The invariant of this
context: nothing it produces ever touches disk or the repository — a diff is
a proposal, and applying it is gated behind human approval
(`Diff.applied` is always `False` here).

## Two paths to a diff

| Tool (router action) | Use case | Who writes the new content |
|----------------------|----------|---------------------------|
| `propose_edit` | `ProposeFixUseCase` | the router supplies `updated` content itself |
| `draft_fix` | `GenerateFixUseCase` | `LLMFixDrafter` — a dedicated drafting prompt |

Both end in the same pure domain service, `build_diff(path, original,
updated)`, which produces a standard `difflib` unified diff
(`a/<path>` → `b/<path>`). The diff lands in workflow state (`diffs` list),
flows into the approval request a human reviews, and into the PR body
after approval.

## The LLM drafter

`LLMFixDrafter` (infrastructure) implements the `FixDrafter` port on top of
the shared LLM port — it works identically with Anthropic, OpenAI, or
Ollama (see [llm-providers.md](llm-providers.md)). Its system prompt
encodes the F-03 criteria directly:

- minimal change — modify only what the root cause requires;
- preserve function signatures;
- match the file's existing style;
- inline comments only where the change needs explanation;
- **never** include secrets, credentials, or new dependencies (S-07, S-04).

The drafter returns the full updated file content as strict JSON; an empty
or missing `updated_content` raises immediately rather than producing an
empty diff. The `guidance` argument carries extra instructions — this is
how human rejection feedback ("try a different approach") reaches the
drafter on a retry pass (F-10).

## Multi-file fixes (F-09)

The router calls `draft_fix` / `propose_edit` once per file; each call
appends one `Diff` to workflow state. All accumulated diffs travel together
into the approval request and, after approval, the PR — so a reviewer
always sees the complete change set, never a partial one.

## Failure behavior

A drafting failure (provider error, empty content) is recorded as a failed
tool result; the workflow keeps routing and the compound-failure guard
(3 consecutive failures → escalate, R-09) prevents infinite retry loops.
See [reliability.md](reliability.md).
