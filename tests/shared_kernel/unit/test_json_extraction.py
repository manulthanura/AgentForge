"""JSON extraction robustness for LLM output parsing."""

from __future__ import annotations

import pytest

from shared_kernel.llm import extract_json

from tests.support.fakes import FakeProvider


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    text = 'Sure!\n```json\n{"action": "finish"}\n```\nDone.'
    assert extract_json(text) == {"action": "finish"}


def test_extract_json_with_surrounding_prose():
    text = 'Here is my decision: {"action": "search_code", "args": {"query": "auth"}} hope that helps'
    assert extract_json(text)["action"] == "search_code"


def test_extract_nested_json():
    text = 'x {"a": {"b": {"c": 3}}} y'
    assert extract_json(text) == {"a": {"b": {"c": 3}}}


def test_extract_json_failure_raises():
    with pytest.raises(ValueError, match="No JSON object"):
        extract_json("I refuse to answer in JSON.")


def test_complete_json_appends_instruction_and_parses():
    provider = FakeProvider(responses=['{"ok": true}'])
    result = provider.complete_json(
        [{"role": "user", "content": "hi"}], system="base prompt"
    )
    assert result == {"ok": True}
    call = provider.calls[0]
    assert call["json_mode"] is True
    assert "base prompt" in call["system"]
    assert "JSON" in call["system"]
