"""Adapter selection is driven purely by the LLM_PROVIDER env var."""

from __future__ import annotations

import pytest

from shared_kernel.config.model_config import ModelConfigStore
from shared_kernel.config.settings import Settings
from shared_kernel.llm import PROVIDERS, LLMProvider, get_provider
from shared_kernel.llm.anthropic_adapter import AnthropicProvider
from shared_kernel.llm.ollama_adapter import OllamaProvider
from shared_kernel.llm.openai_adapter import OpenAIProvider


@pytest.mark.parametrize(
    ("env_value", "expected_cls"),
    [
        ("anthropic", AnthropicProvider),
        ("openai", OpenAIProvider),
        ("ollama", OllamaProvider),
    ],
)
def test_env_var_selects_provider(monkeypatch, fake_keys, env_value, expected_cls):
    """Switching LLM_PROVIDER between anthropic/openai/ollama needs no code change."""
    monkeypatch.setenv("LLM_PROVIDER", env_value)
    provider = get_provider(Settings())
    assert isinstance(provider, expected_cls)
    assert isinstance(provider, LLMProvider)
    assert provider.name == env_value
    assert provider.model == expected_cls.default_model


def test_default_provider_is_anthropic(monkeypatch, fake_keys):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(get_provider(Settings()), AnthropicProvider)


def test_provider_value_is_case_insensitive(monkeypatch, fake_keys):
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    assert isinstance(get_provider(Settings()), OpenAIProvider)


def test_unknown_provider_raises_with_valid_choices(monkeypatch, fake_keys):
    monkeypatch.setenv("LLM_PROVIDER", "grok")
    with pytest.raises(ValueError, match="anthropic.*ollama.*openai"):
        get_provider(Settings())


@pytest.mark.parametrize("env_value", ["anthropic", "openai", "ollama"])
def test_model_override_via_env(monkeypatch, fake_keys, env_value):
    monkeypatch.setenv("LLM_PROVIDER", env_value)
    monkeypatch.setenv("LLM_MODEL", "custom-model-x")
    assert get_provider(Settings()).model == "custom-model-x"


def test_model_config_json_drives_default_model(monkeypatch, fake_keys, tmp_path):
    config = tmp_path / "model_config.json"
    config.write_text('{"anthropic": "claude-from-config"}', encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    provider = get_provider(Settings(), model_config=ModelConfigStore(config))
    assert provider.model == "claude-from-config"


def test_registry_covers_all_required_providers():
    assert {"anthropic", "openai", "ollama"} <= set(PROVIDERS)
