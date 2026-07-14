"""GitHub webhook receiver + workflow status endpoint.

Every webhook is HMAC-verified against GITHUB_WEBHOOK_SECRET (S-06) before
any payload parsing.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from shared_kernel.security import verify_github_signature

router = APIRouter(tags=["workflows"])


@router.post("/webhooks/github")
async def github_webhook(request: Request):
    body = await request.body()
    settings = request.app.state.settings
    if not verify_github_signature(
        settings.github_webhook_secret,
        body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature.")

    if request.headers.get("X-GitHub-Event") != "issues":
        return {"ignored": True, "reason": "unsupported event"}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Malformed JSON body.") from exc
    if payload.get("action") != "opened":
        return {"ignored": True, "reason": f"action={payload.get('action')!r}"}

    gh_issue = payload.get("issue") or {}
    issue = {
        "number": int(gh_issue.get("number", 0)),
        "title": gh_issue.get("title", ""),
        "body": gh_issue.get("body") or "",
        "labels": [label.get("name", "") for label in gh_issue.get("labels", [])],
    }
    workflow_id = f"issue-{issue['number']}"

    application = request.app.state.application
    final_state = application.run_workflow.execute(
        workflow_id, issue, workspace=settings.workspace_path
    )
    return {
        "workflow_id": workflow_id,
        "status": final_state.get("status"),
        "classification": final_state.get("classification"),
        "awaiting_approval": bool(final_state.get("pending_approval"))
        and final_state.get("status") == "awaiting_approval",
    }


@router.get("/workflows/{workflow_id}")
def workflow_status(workflow_id: str, request: Request):
    engine = request.app.state.application.engine
    state = engine.get_state(workflow_id)
    if not state:
        raise HTTPException(
            status_code=404, detail=f"Unknown workflow {workflow_id!r}"
        )
    return {
        "workflow_id": workflow_id,
        "status": state.get("status"),
        "classification": state.get("classification"),
        "decisions": state.get("decisions", []),
        "step_count": state.get("step_count", 0),
        "pull_request": state.get("pull_request"),
    }
