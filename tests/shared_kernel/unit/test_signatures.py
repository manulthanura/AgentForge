"""Webhook HMAC verification (S-06: forged payloads must be rejected)."""

from __future__ import annotations

import hashlib
import hmac
import time

from shared_kernel.security import verify_github_signature, verify_slack_signature

SECRET = "s3cret"
BODY = b'{"action": "opened"}'


def _github_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _slack_sig(secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


# --- GitHub ---------------------------------------------------------------


def test_github_valid_signature_accepted():
    assert verify_github_signature(SECRET, BODY, _github_sig(SECRET, BODY))


def test_github_forged_signature_rejected():
    assert not verify_github_signature(SECRET, BODY, _github_sig("wrong", BODY))


def test_github_tampered_body_rejected():
    signature = _github_sig(SECRET, BODY)
    assert not verify_github_signature(SECRET, b'{"action": "evil"}', signature)


def test_github_missing_secret_or_header_fails_closed():
    assert not verify_github_signature(None, BODY, _github_sig(SECRET, BODY))
    assert not verify_github_signature(SECRET, BODY, None)


# --- Slack ----------------------------------------------------------------


def test_slack_valid_signature_accepted():
    ts = str(int(time.time()))
    assert verify_slack_signature(SECRET, ts, BODY, _slack_sig(SECRET, ts, BODY))


def test_slack_forged_signature_rejected():
    ts = str(int(time.time()))
    assert not verify_slack_signature(SECRET, ts, BODY, _slack_sig("wrong", ts, BODY))


def test_slack_replayed_timestamp_rejected():
    stale = str(int(time.time()) - 3600)
    assert not verify_slack_signature(
        SECRET, stale, BODY, _slack_sig(SECRET, stale, BODY)
    )


def test_slack_garbage_timestamp_rejected():
    assert not verify_slack_signature(SECRET, "not-a-ts", BODY, "v0=abc")
