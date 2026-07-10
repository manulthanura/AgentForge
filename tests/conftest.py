"""Shared fixtures for all test suites. No network calls are made anywhere."""

from __future__ import annotations

import os

import pytest

# Tests must never emit telemetry, regardless of what the local .env enables.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

# Approval gates are opt-in per test: Phase 1/2 workflow tests run ungated;
# Phase 3 tests monkeypatch REQUIRE_APPROVAL=true explicitly.
os.environ["REQUIRE_APPROVAL"] = "false"

SAMPLE_ISSUE = {
    "number": 42,
    "title": "Login fails when email contains '+' character",
    "body": "Steps to reproduce: register with alice+test@example.com, login fails.",
    "labels": ["bug"],
}

VAGUE_ISSUE = {
    "number": 43,
    "title": "It doesn't work",
    "body": "please fix",
    "labels": [],
}


@pytest.fixture
def sample_issue():
    return dict(SAMPLE_ISSUE)


@pytest.fixture
def vague_issue():
    return dict(VAGUE_ISSUE)


@pytest.fixture
def fake_keys(monkeypatch):
    """Fake credentials so adapters can be constructed without real keys."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
