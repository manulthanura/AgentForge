# LLM Providers

All LLM access goes through one port — `LLMProvider` in
`src/shared_kernel/llm/port.py` — with seven adapters selected purely by
configuration. No agent code imports a provider SDK directly: every adapter
is built on a [LangChain](https://docs.langchain.com/) chat model integration
rather than a raw vendor client, so message conversion, token-usage
extraction, and error mapping are shared in one place
(`shared_kernel/llm/langchain_support.py`) instead of duplicated seven times.

## Switching providers

```bash
LLM_PROVIDER=anthropic    # Claude (default) — needs ANTHROPIC_API_KEY
LLM_PROVIDER=openai       # GPT — needs OPENAI_API_KEY
LLM_PROVIDER=ollama       # local models — needs a running Ollama, no key
LLM_PROVIDER=openrouter   # any OpenRouter-hosted model — needs OPENROUTER_API_KEY
LLM_PROVIDER=azure        # Azure OpenAI — needs AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT
LLM_PROVIDER=gemini       # Google Gemini — needs GOOGLE_API_KEY
LLM_PROVIDER=huggingface  # Hugging Face models — needs HUGGINGFACEHUB_API_TOKEN
```

That's the entire change. The factory (`shared_kernel/llm/factory.py`)
instantiates the matching adapter; the graph, router, and use cases are
untouched.

| Provider | Package | Class |
|----------|---------|-------|
| `anthropic` | `langchain-anthropic` | `ChatAnthropic` |
| `openai` | `langchain-openai` | `ChatOpenAI` |
| `ollama` | `langchain-ollama` | `ChatOllama` |
| `openrouter` | `langchain-openai` | `ChatOpenAI` pointed at OpenRouter's base URL |
| `azure` | `langchain-openai` | `AzureChatOpenAI` |
| `gemini` | `langchain-google-genai` | `ChatGoogleGenerativeAI` |
| `huggingface` | `langchain-huggingface` | `ChatHuggingFace` + `HuggingFaceEndpoint` |

OpenRouter proxies many upstream providers (OpenAI, Anthropic, Meta, Google,
...) behind one OpenAI-compatible Chat Completions endpoint, so the adapter
reuses `ChatOpenAI` pointed at `OPENROUTER_BASE_URL`
(default `https://openrouter.ai/api/v1`) instead of adding a new dependency.
Model names are OpenRouter slugs — `<upstream-provider>/<model>`, e.g.
`anthropic/claude-sonnet-4.5` or `meta-llama/llama-3.1-70b-instruct` — set
via `LLM_MODEL` or `model_config.json`, same as every other provider.
`OPENROUTER_SITE_URL` / `OPENROUTER_APP_NAME` are optional attribution
headers OpenRouter shows on its public leaderboards; leave them blank to
omit. OpenRouter (and any other OpenAI-compatible endpoint) can return HTTP
200 with a null `choices` and an embedded `error` instead of an HTTP error
status — `langchain-openai` turns that into `ValueError(error_dict)`, which
`langchain_support.raise_as_llm_error` recognizes and maps to
`LLMUnavailableError` (or `LLMRateLimitError` if the payload carries a `429`
code) rather than a generic, non-retryable `LLMError`.

Other config specifics:

- **Anthropic**: `ChatAnthropic` is configured with `thinking={"type":
  "adaptive"}` at construction (extended thinking). Its content can be a list
  of blocks (thinking + text) rather than a plain string — `response_text()`
  in `langchain_support.py` extracts just the text via `AIMessage.text`,
  which handles both shapes. A `stop_reason` of `"refusal"` raises `LLMError`
  immediately rather than returning a declined response as if it succeeded.
- **Ollama**: `validate_model_on_init=False` (the default) so construction
  never probes the server — no network call until the first `complete()`.
- **Azure**: `AZURE_OPENAI_ENDPOINT` (your resource URL),
  `AZURE_OPENAI_API_VERSION` (default `2024-10-21`), and
  `AZURE_OPENAI_DEPLOYMENT` (falls back to the resolved model name if unset —
  set it explicitly when your Azure deployment name differs from the model).
- **Gemini**: just `GOOGLE_API_KEY`. `json_mode` stays prompt-level (see
  below) rather than binding a native `response_mime_type`, to avoid coupling
  to a specific `langchain-google-genai` version's kwarg.
- **Hugging Face**: `HUGGINGFACEHUB_API_TOKEN` plus `LLM_MODEL` /
  `model_config.json` as a `repo_id` for serverless Inference Providers.
  The chat model is constructed lazily on first `complete()` call rather than
  at adapter construction — `ChatHuggingFace` resolves a tokenizer for
  chat-template formatting, which can hit the network, and that must never
  happen just from instantiating the provider.

## Models

| Provider | Default model | Source |
|----------|--------------|--------|
| anthropic | `claude-opus-4-8` | `shared_kernel/config/model_config.json` |
| openai | `gpt-4o` | 〃 |
| ollama | `llama3.1` | 〃 |
| openrouter | `openai/gpt-4o` | 〃 |
| azure | `gpt-4o` | 〃 |
| gemini | `gemini-2.5-flash` | 〃 |
| huggingface | `meta-llama/Llama-3.1-8B-Instruct` | 〃 |

Precedence: `LLM_MODEL` env override → `model_config.json` → adapter's
built-in default. Update at runtime without a deploy:

```bash
curl -X PATCH http://localhost:8000/admin/model-config \
  -H "X-Admin-Token: $SECRET_KEY" -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "model": "claude-opus-4-8"}'
```

## The port contract

- `complete(messages, system=..., max_tokens=..., json_mode=...)` returns a
  normalized `LLMResponse` (text, model, stop_reason, token counts, raw).
- `complete_json(...)` adds a strict-JSON instruction and parses the reply
  tolerantly (code fences, surrounding prose, nested objects) via
  `extract_json`.
- `json_mode` uses native enforcement where the provider has it
  (OpenAI/Azure/OpenRouter `response_format`, Ollama `format: json`) and
  prompt-level instruction elsewhere (Anthropic, Gemini, Hugging Face — see
  above).

## Failure semantics (used by the retry layer)

| Provider response | Raised as | Retried? |
|-------------------|-----------|----------|
| 429 | `LLMRateLimitError` (carries `retry_after`) | yes, honoring the server cooldown |
| 5xx / 529 overloaded / connection error | `LLMUnavailableError` | yes, backoff 2s→4s→8s |
| 4xx, refusal, malformed | `LLMError` | never |

`RetryingLLMProvider` wraps whichever adapter the factory produced (wired in
`src/bootstrap.py`); see
[reliability.md](reliability.md) for the policy details.

## Adding another provider

1. New adapter in `shared_kernel/llm/<name>_adapter.py` implementing
   `complete` and mapping failures to the typed errors above. If it's built
   on a LangChain chat model, reuse `shared_kernel/llm/langchain_support.py`
   for message conversion, token-usage extraction, and error mapping instead
   of duplicating that logic (see `azure_openai_adapter.py` for the pattern).
2. Register it in `PROVIDERS` in `factory.py`.
3. Add its default model to `model_config.json`.
4. The parametrized tests in `tests/shared_kernel/unit/test_llm_factory.py`
   show the expected behavior contract.
