"""Webhook signature verification (S-06: approval/webhook bypass).

Constant-time comparisons throughout; a missing secret always fails closed.
"""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_github_signature(
    secret: str | None, body: bytes, signature_header: str | None
) -> bool:
    """Validate GitHub's X-Hub-Signature-256 header (sha256=<hexdigest>)."""
    if not secret or not signature_header:
        return False
    expected = (
        "sha256="
        + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def verify_slack_signature(
    secret: str | None,
    timestamp: str | None,
    body: bytes,
    signature_header: str | None,
    *,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> bool:
    """Validate Slack's X-Slack-Signature (v0=<hexdigest>) with replay guard."""
    if not secret or not timestamp or not signature_header:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = now if now is not None else time.time()
    if abs(current - ts) > tolerance_seconds:
        return False  # replayed or badly skewed request
    basestring = b"v0:" + timestamp.encode("utf-8") + b":" + body
    expected = (
        "v0="
        + hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)
