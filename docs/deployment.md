# Deployment

How to run AgentForge somewhere other than your laptop. The unit of
deployment is the single image built by `docker/Dockerfile`; the reference
topology is `docker/docker-compose.yml`.

## The image

`python:3.12-slim` + uv-installed locked dependencies (`uv sync --frozen`),
source, and migrations. Three commands, same image:

| Role | Command |
|------|---------|
| API server | `uvicorn --factory interfaces.http.app:create_app --host 0.0.0.0 --port 8000` |
| Migrations (one-shot) | `python main.py migrate` |
| Demo run | `python main.py demo` (the image default) |

Build from the repo root (the compose file already does this):

```bash
docker build -f docker/Dockerfile -t agentforge .
```

## Reference topology (compose)

```
postgres (16-alpine, healthcheck)
   └── migrate  — runs migrations, must exit 0
         └── app — the API, starts only after migrate succeeds
```

The same order applies on any platform: **run migrations as a release/init
step, then start the app**. Migrations are idempotent (each file is
recorded once), so re-running on every deploy is safe.

## Configuration in production

Everything is environment variables — see `.env.example` for the full
catalog. The ones that change character in production:

| Variable | Production guidance |
|----------|--------------------|
| `DATABASE_URL` | a managed Postgres (14–16); this holds checkpoints — losing it loses paused workflows |
| `LLM_PROVIDER` + its API key | set a real provider; the compose default (`ollama`) exists only so the stack boots without keys |
| `GITHUB_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET` | **required** — webhook endpoints fail closed (401) without them, so unset means unusable, not insecure |
| `SECRET_KEY` | set it, or the admin API stays disabled (503) |
| `GITHUB_TOKEN` + `GITHUB_REPO` | enable real issue reads and PR creation |
| `APP_ENV`, `LOG_LEVEL` | `production`, `info` |

Model names are deliberately **not** env vars — change them at runtime via
`PATCH /admin/model-config`
([ADR-007](architecture/adr/007-model-names-outside-env.md)).

## Exposing webhooks

GitHub and Slack must reach the service over HTTPS. Point:

- the GitHub repo webhook (`issues` events, content type JSON, the secret
  set to `GITHUB_WEBHOOK_SECRET`) at `https://<host>/webhooks/github`;
- the Slack app's interactivity URL at
  `https://<host>/webhooks/slack/interactions`.

Terminate TLS at your ingress/load balancer; the app itself serves plain
HTTP on 8000. For local development, a tunnel (`ngrok http 8000`,
`cloudflared tunnel`) works with the same URLs.

## Monitoring

- **Liveness**: `GET /healthz` → `{"ok": true, "provider": "..."}` — wire
  it to your platform's health probe.
- **Traces**: set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` and
  every workflow appears in LangSmith as `agentforge:<workflow_id>`
  (see [features/observability.md](features/observability.md)).
- **Decision log**: one JSON line per agent decision on the
  `agentforge.decisions` logger — ship stdout to your log stack and you
  have a queryable audit trail with zero extra infrastructure.
- **Approval hygiene**: schedule `HandleTimeoutUseCase` (cron / scheduler
  of your platform) so pending approvals get their 48h reminder and 72h
  timeout.

## Scaling notes

- The app is stateless — all workflow state lives in Postgres checkpoints —
  so multiple replicas behind a load balancer are fine; any replica can
  resume any workflow.
- Redis/Celery variables exist in `.env.example` for queue-based webhook
  processing (S-08 rate-limit absorption); the queue worker itself is not
  yet part of the stack.
- Postgres is the component worth paying for: backups and PITR protect the
  paused workflows and audit history.
