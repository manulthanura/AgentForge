# ADR-005: Provider-Agnostic LLM Port with Env-Selected Adapters

**Status**: accepted

## Context

The agent must run against Claude, GPT, a local model via Ollama, or any
model reachable through a router like OpenRouter (C-03), and switching must
never require a code change.

## Decision

A single `LLMProvider` port in `shared_kernel/llm` (`complete` /
`complete_json` returning a normalized `LLMResponse`). Four adapters —
`AnthropicProvider`, `OpenAIProvider`, `OllamaProvider`,
`OpenRouterProvider` — are selected at runtime by the `LLM_PROVIDER` env var
through a factory registry. No LangGraph node, use case, or router ever
imports a provider SDK. `OpenRouterProvider` reuses the `openai` SDK against
OpenRouter's OpenAI-compatible endpoint rather than adding a dependency,
since OpenRouter is itself a proxy in front of many upstream providers.

Failure classification is part of the port contract: adapters map 429 to
`LLMRateLimitError` (carrying Retry-After) and 5xx/connection errors to
`LLMUnavailableError`, so the retry decorator (`RetryingLLMProvider`) works
identically across providers.

## Trade-offs

The port is deliberately narrow (no native tool-calling, no streaming) —
the router works via strict-JSON prompting instead, which the weakest
supported backend (a local Ollama model) can also satisfy. Provider-native
structured outputs can be added per-adapter later without changing callers.
