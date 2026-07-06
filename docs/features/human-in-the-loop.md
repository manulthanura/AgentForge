# Human-in-the-Loop Approval

No irreversible action without human sign-off. With `REQUIRE_APPROVAL=true`
(the default) every workflow that reaches `finish` pauses at an approval
gate instead of finalizing.

## The flow

1. The router decides the workflow is ready (`finish`).
2. **notify_approval** persists an `ApprovalRequest` (status `pending`) and
   sends the reviewer a message containing everything needed to decide in
   30 seconds (U-01): issue summary, proposed diffs, test results, risk
   assessment, and an Approve/Reject prompt. Delivery failure never blocks
   the pause — the request is stored either way.
3. **await_approval** interrupts the graph; the workflow checkpoints with
   status `awaiting_approval` and stops consuming resources.
4. A human clicks Approve or Reject in Slack. The signed interaction hits
   `POST /webhooks/slack/interactions`, `HandleApprovalResponseUseCase`
   records the decision, and `ResumeWorkflowUseCase` re-enters the graph
   from the checkpoint — with full pre-pause state, even days later (F-07).

## Decisions

| Decision | What happens |
|----------|--------------|
| Approve | `finalize` → status `done` |
| Reject + feedback | feedback lands in the router context as `human_feedback` (highest-priority instruction); the workflow re-plans, then pauses at a fresh gate |
| Reject > `MAX_APPROVAL_RETRIES` (3) | escalate — the agent stops and reports |
| Nobody responds | timeout sweep (below) |

Concurrent workflows are fully independent: approving issue #42 resumes
only issue #42; #43 and #44 stay paused with their own state.

## Timeouts

`HandleTimeoutUseCase` sweeps pending requests (wire it to a scheduler or
run ad hoc):

- older than `APPROVAL_REMINDER_HOURS` (48) → one reminder notification
  (never repeated);
- older than `APPROVAL_TIMEOUT_HOURS` (72) → request marked `timed_out`.
  The workflow's checkpoint stays valid for manual resume (R-07).

## Notifications

The `Notifier` port has two adapters, selected by configuration:

| Channel | Adapter | Enabled by |
|---------|---------|-----------|
| Slack | `SlackNotifier` (incoming webhook) | `SLACK_WEBHOOK_URL` (+ `SLACK_APPROVAL_CHANNEL`) |
| Email | `EmailNotifier` (SMTP) | `SMTP_HOST` + `SMTP_TO` |

## Security (S-06)

A forged approval must never resume a workflow. Every Slack interaction is
HMAC-verified (`v0` signature + 5-minute replay window) against
`SLACK_SIGNING_SECRET` *before* the payload is parsed; failures return 401
and the workflow stays paused. Unknown or already-settled approvals return
404 — a decision can't be applied twice.
