"""Slack interactions endpoint: Approve / Reject button clicks.

Every request is HMAC-verified against SLACK_SIGNING_SECRET (S-06) before
any payload parsing — a forged approval must never resume a workflow.
"""

from __future__ import annotations

import json
import urllib.parse

from fastapi import APIRouter, HTTPException, Request

from shared_kernel.security import verify_slack_signature

from ..application.handle_response import UnknownApprovalError

router = APIRouter(prefix="/webhooks/slack", tags=["approval"])


@router.post("/interactions")
async def slack_interaction(request: Request):
    body = await request.body()
    settings = request.app.state.settings
    if not verify_slack_signature(
        settings.slack_signing_secret,
        request.headers.get("X-Slack-Request-Timestamp"),
        body,
        request.headers.get("X-Slack-Signature"),
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    workflow_id, approved, feedback = _parse_interaction(body)

    handle_response = request.app.state.application.handle_approval_response
    try:
        final_state = handle_response.execute(workflow_id, approved, feedback)
    except UnknownApprovalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "workflow_id": workflow_id,
        "approved": approved,
        "status": final_state.get("status"),
    }


def _parse_interaction(body: bytes) -> tuple[str, bool, str]:
    """Extract (workflow_id, approved, feedback) from a Slack interaction."""
    form = urllib.parse.parse_qs(body.decode("utf-8"))
    raw_payload = form.get("payload", [None])[0]
    if not raw_payload:
        raise HTTPException(status_code=422, detail="Missing interaction payload.")
    try:
        payload = json.loads(raw_payload)
        action = payload["actions"][0]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise HTTPException(
            status_code=422, detail="Malformed interaction payload."
        ) from exc

    action_id = str(action.get("action_id", ""))
    if action_id not in {"approve", "reject"}:
        raise HTTPException(
            status_code=422, detail=f"Unsupported action {action_id!r}."
        )

    # value is either a plain workflow_id or {"workflow_id": ..., "feedback": ...}
    value = action.get("value", "")
    feedback = ""
    workflow_id = value
    try:
        parsed_value = json.loads(value)
        if isinstance(parsed_value, dict):
            workflow_id = str(parsed_value.get("workflow_id", ""))
            feedback = str(parsed_value.get("feedback", ""))
    except (json.JSONDecodeError, TypeError):
        pass
    if not workflow_id:
        raise HTTPException(status_code=422, detail="Missing workflow_id.")

    return workflow_id, action_id == "approve", feedback
