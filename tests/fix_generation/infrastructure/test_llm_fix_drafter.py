"""LLMFixDrafter + GenerateFixUseCase: LLM-drafted fixes become diffs."""

from __future__ import annotations

import json

import pytest

from fix_generation.application.generate_fix import GenerateFixUseCase
from fix_generation.application.ports import FixDrafter
from fix_generation.infrastructure.llm_fix_drafter import LLMFixDrafter
from shared_kernel.llm import LLMError

from tests.support.fakes import FailingProvider, FakeProvider

ORIGINAL = "def login(email):\n    return email\n"
UPDATED = "def login(email):\n    return sanitize(email)\n"


def _drafter(updated=UPDATED):
    provider = FakeProvider(
        responses=[
            json.dumps({"updated_content": updated, "explanation": "sanitize input"})
        ]
    )
    return LLMFixDrafter(provider), provider


def test_drafter_implements_port():
    drafter, _ = _drafter()
    assert isinstance(drafter, FixDrafter)


def test_draft_returns_updated_content_and_carries_context(sample_issue):
    drafter, provider = _drafter()
    analysis = {"issue_type": "bug", "affected_area": "authentication"}

    updated = drafter.draft(sample_issue, analysis, "src/auth/login.py", ORIGINAL)

    assert updated == UPDATED
    prompt = provider.calls[0]["messages"][0]["content"]
    assert "'+'" in prompt  # issue title present
    assert "authentication" in prompt  # analysis present
    assert "src/auth/login.py" in prompt  # target file present
    assert "def login" in prompt  # original content present


def test_generate_fix_use_case_produces_reviewable_diff(sample_issue):
    drafter, _ = _drafter()
    diff = GenerateFixUseCase(drafter).execute(
        sample_issue, None, "src/auth/login.py", ORIGINAL
    )
    assert diff.applied is False
    assert "-    return email" in diff.content
    assert "+    return sanitize(email)" in diff.content
    assert diff.path == "src/auth/login.py"


def test_missing_updated_content_raises(sample_issue):
    provider = FakeProvider(responses=['{"explanation": "no content"}'])
    drafter = LLMFixDrafter(provider)
    with pytest.raises(ValueError, match="no updated_content"):
        drafter.draft(sample_issue, None, "a.py", ORIGINAL)


def test_provider_outage_propagates_as_llm_error(sample_issue):
    drafter = LLMFixDrafter(FailingProvider())
    with pytest.raises(LLMError):
        drafter.draft(sample_issue, None, "a.py", ORIGINAL)
