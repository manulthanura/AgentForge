# HTTP API

One FastAPI app (`src/interfaces/http/app.py`) composed from each bounded
context's router. Interactive docs at `/docs` when the app is running.

Start it: `docker compose -f docker/docker-compose.yml up -d` (port 8000)
or locally
`uv run uvicorn --app-dir src --factory interfaces.http.app:create_app`.

## Endpoints

| Method + path | Context | Purpose |
|---------------|---------|---------|
| `POST /webhooks/github` | workflow_orchestration | GitHub `issues/opened` events start a workflow |
| `GET /workflows/{workflow_id}` | workflow_orchestration | status, classification, decision log, step count |
| `POST /webhooks/slack/interactions` | approval | Approve/Reject button clicks resume paused workflows |
| `GET /admin/model-config` | shared_kernel | current per-provider default models |
| `PATCH /admin/model-config` | shared_kernel | change a provider's default model at runtime |
| `GET /healthz` | — | liveness + active LLM provider |

## Webhook signatures (S-06)

Both webhook endpoints verify HMAC signatures on the **raw body** before
parsing anything, and fail closed (missing secret ⇒ every request is 401).

**GitHub** — `X-Hub-Signature-256: sha256=<hexdigest>`, HMAC-SHA256 with
`GITHUB_WEBHOOK_SECRET` (exactly what GitHub sends when you set the webhook
secret). Events other than `issues` / actions other than `opened` are
acknowledged and ignored.

**Slack** — `X-Slack-Signature: v0=<hexdigest>` over
`v0:<timestamp>:<body>` with `SLACK_SIGNING_SECRET`, plus a 5-minute
timestamp window against replays.

`tests/support/signing.py` contains reference implementations of both
signing schemes.

## Workflow start

```
POST /webhooks/github
X-GitHub-Event: issues
X-Hub-Signature-256: sha256=...

{"action": "opened", "issue": {"number": 42, "title": "...",
 "body": "...", "labels": [{"name": "bug"}]}}
```

Response:

```json
{"workflow_id": "issue-42", "status": "awaiting_approval",
 "classification": "bug", "awaiting_approval": true}
```

(`status` is `awaiting_clarification` for vague issues, `done` when
`REQUIRE_APPROVAL=false`, `escalated` on unrecoverable failure.)

## Approval interaction

Slack `block_actions` payload, form-encoded as Slack sends it. The button's
`action_id` must be `approve` or `reject`; its `value` is either the plain
workflow id or `{"workflow_id": "...", "feedback": "..."}` (feedback is
fed to the router on rejection).

Response: `{"workflow_id": "issue-42", "approved": true, "status": "done"}`.
`404` for unknown/already-settled approvals; `401` for bad signatures;
nothing resumes in either case.

## Admin: model config

```bash
curl -X PATCH http://localhost:8000/admin/model-config \
  -H "X-Admin-Token: $SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"provider": "openai", "model": "gpt-4o"}'
```

`503` when `SECRET_KEY` is unset (the admin API is disabled), `401` on a
wrong token, `422` for unknown providers.
