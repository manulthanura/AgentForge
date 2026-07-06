"""HMAC signing helpers mirroring GitHub's and Slack's webhook signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse


def github_headers(secret: str, body: bytes) -> dict[str, str]:
    signature = (
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    )
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": "issues",
        "Content-Type": "application/json",
    }


def slack_interaction(
    secret: str,
    action_id: str,
    workflow_id: str,
    feedback: str = "",
) -> tuple[bytes, dict[str, str]]:
    """Build a signed Slack block_actions interaction request."""
    value = json.dumps({"workflow_id": workflow_id, "feedback": feedback})
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": action_id, "value": value}],
    }
    body = urllib.parse.urlencode({"payload": json.dumps(payload)}).encode()
    timestamp = str(int(time.time()))
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return body, {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def github_issue_event(number: int, title: str, body: str, labels: list[str]) -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "issue": {
                "number": number,
                "title": title,
                "body": body,
                "labels": [{"name": name} for name in labels],
            },
        }
    ).encode()
