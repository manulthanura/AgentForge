"""Adapter selection via the LLM_PROVIDER environment variable."""

from __future__ import annotations

from ..config.model_config import ModelConfigStore
from ..config.settings import Settings, get_settings
from .anthropic_adapter import AnthropicProvider
from .ollama_adapter import OllamaProvider
from .openai_adapter import OpenAIProvider
from .openrouter_adapter import OpenRouterProvider
from .port import LLMProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    AnthropicProvider.name: AnthropicProvider,
    OpenAIProvider.name: OpenAIProvider,
    OllamaProvider.name: OllamaProvider,
    OpenRouterProvider.name: OpenRouterProvider,
}


def get_provider(
    settings: Settings | None = None,
    model_config: ModelConfigStore | None = None,
) -> LLMProvider:
    """Instantiate the adapter named by LLM_PROVIDER (anthropic|openai|ollama|openrouter)."""
    settings = settings or get_settings()
    provider_cls = PROVIDERS.get(settings.llm_provider)
    if provider_cls is None:
        valid = ", ".join(sorted(PROVIDERS))
        raise ValueError(
            f"Unknown LLM_PROVIDER {settings.llm_provider!r}; expected one of: {valid}"
        )
    model_config = model_config or ModelConfigStore()
    return provider_cls(settings, model=model_config.default_model(provider_cls.name))
