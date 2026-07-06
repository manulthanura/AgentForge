# LLM Providers

All LLM access goes through one port — `LLMProvider` in
`src/shared_kernel/llm/port.py` — with three adapters selected purely by
configuration. No agent code imports a provider SDK.

## Switching providers

```bash
LLM_PROVIDER=anthropic   # Claude (default) — needs ANTHROPIC_API_KEY
LLM_PROVIDER=openai      # GPT — needs OPENAI_API_KEY
LLM_PROVIDER=ollama      # local models — needs a running Ollama, no key
```

That's the entire change. The factory (`shared_kernel/llm/factory.py`)
instantiates the matching adapter; the graph, router, and use cases are
untouched.

## Models

| Provider | Default model | Source |
|----------|--------------|--------|
| anthropic | `claude-opus-4-8` | `shared_kernel/config/model_config.json` |
| openai | `gpt-4o` | 〃 |
| ollama | `llama3.1` | 〃 |

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
  (OpenAI `response_format`, Ollama `format: json`) and prompt-level
  instruction elsewhere.

## Failure semantics (used by the retry layer)

| Provider response | Raised as | Retried? |
|-------------------|-----------|----------|
| 429 | `LLMRateLimitError` (carries `retry_after`) | yes, honoring the server cooldown |
| 5xx / 529 overloaded / connection error | `LLMUnavailableError` | yes, backoff 2s→4s→8s |
| 4xx, refusal, malformed | `LLMError` | never |

`RetryingLLMProvider` wraps whichever adapter the factory produced (wired in
`src/bootstrap.py`); see
[reliability.md](reliability.md) for the policy details.

## Adding a fourth provider

1. New adapter in `shared_kernel/llm/<name>_adapter.py` implementing
   `complete` and mapping failures to the typed errors above.
2. Register it in `PROVIDERS` in `factory.py`.
3. Add its default model to `model_config.json`.
4. The parametrized tests in `tests/shared_kernel/unit/test_llm_factory.py`
   show the expected behavior contract.
