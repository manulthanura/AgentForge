# ADR-005: Provider-Agnostic LLM Port with Env-Selected Adapters

**Status**: accepted

## Context

The agent must run against Claude, GPT, a local model via Ollama, any model
reachable through a router like OpenRouter (C-03), or Azure OpenAI / Gemini /
Hugging Face, and switching must never require a code change.

## Decision

A single `LLMProvider` port in `shared_kernel/llm` (`complete` /
`complete_json` returning a normalized `LLMResponse`). Seven adapters —
`AnthropicProvider`, `OpenAIProvider`, `OllamaProvider`, `OpenRouterProvider`,
`AzureOpenAIProvider`, `GeminiProvider`, `HuggingFaceProvider` — are selected
at runtime by the `LLM_PROVIDER` env var through a factory registry. No
LangGraph node, use case, or router ever imports a provider SDK directly:
every adapter is built on a LangChain chat model integration
(`langchain-anthropic`, `langchain-openai`, `langchain-ollama`,
`langchain-google-genai`, `langchain-huggingface`) instead of a raw vendor
client, and message conversion, token-usage extraction, and error mapping are
shared once in `langchain_support.py` rather than duplicated per adapter.
`OpenRouterProvider` reuses `ChatOpenAI` against OpenRouter's OpenAI-compatible
endpoint rather than adding a dependency, since OpenRouter is itself a proxy
in front of many upstream providers.

Failure classification is part of the port contract: adapters map 429 to
`LLMRateLimitError` (carrying Retry-After) and 5xx/connection errors to
`LLMUnavailableError`, so the retry decorator (`RetryingLLMProvider`) works
identically across providers. Status codes are recovered by duck-typing
(`status_code`/`code`/`.response.status_code`) since the underlying SDKs
LangChain wraps don't share one exception hierarchy.

## Trade-offs

The port is deliberately narrow (no native tool-calling, no streaming) —
the router works via strict-JSON prompting instead, which the weakest
supported backend (a local Ollama model) can also satisfy. Provider-native
structured outputs can be added per-adapter later without changing callers.

Building every adapter on LangChain rather than each vendor's raw SDK adds
one more dependency layer, but it means new providers (Azure, Gemini,
Hugging Face) reuse a maintained integration and the same message/error
mapping instead of a bespoke HTTP client each — and it costs nothing at the
port boundary, since `LLMProvider.complete()` never leaks a LangChain type
to callers.
