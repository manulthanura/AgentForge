"""Tracing switch and structured decision logging."""

from __future__ import annotations

import json
import logging
import os

from shared_kernel.config.settings import Settings
from shared_kernel.observability import DecisionLogger, init_tracing


def _settings(monkeypatch, **env) -> Settings:
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return Settings()


def test_tracing_enabled_with_key(monkeypatch):
    settings = _settings(
        monkeypatch,
        LANGCHAIN_TRACING_V2="true",
        LANGCHAIN_API_KEY="ls-key",
        LANGCHAIN_PROJECT="agentforge-test",
    )
    assert init_tracing(settings) is True
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_PROJECT"] == "agentforge-test"


def test_tracing_disabled_without_key(monkeypatch):
    settings = _settings(
        monkeypatch,
        LANGCHAIN_TRACING_V2="true",
        LANGCHAIN_API_KEY=None,
        LANGSMITH_API_KEY=None,
    )
    assert init_tracing(settings) is False
    # Half-configured tracing is hard-disabled to avoid auth-error spam.
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_tracing_disabled_when_off(monkeypatch):
    settings = _settings(
        monkeypatch, LANGCHAIN_TRACING_V2="false", LANGCHAIN_API_KEY="ls-key"
    )
    assert init_tracing(settings) is False


def test_decision_logger_emits_json(caplog):
    logger = DecisionLogger()
    with caplog.at_level(logging.INFO, logger="agentforge.decisions"):
        logger.log(
            "wf-42",
            {"node": "route", "action": "search_code", "reasoning": "find auth"},
        )
    record = json.loads(caplog.records[0].message)
    assert record == {
        "workflow_id": "wf-42",
        "node": "route",
        "action": "search_code",
        "reasoning": "find auth",
    }
