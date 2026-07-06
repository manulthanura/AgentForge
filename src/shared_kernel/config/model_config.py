"""Default model per LLM provider, kept out of env files by design.

The store is file-backed so the admin endpoint can retune models at runtime
without a deploy (and without touching credentials in .env).
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "model_config.json"


class ModelConfigStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self._path = Path(path)
        self._models: dict[str, str] = json.loads(
            self._path.read_text(encoding="utf-8")
        )

    def default_model(self, provider_name: str) -> str | None:
        return self._models.get(provider_name)

    def all_models(self) -> dict[str, str]:
        return dict(self._models)

    def set_default(self, provider_name: str, model: str) -> None:
        """Update one provider's default model and persist it."""
        self._models[provider_name] = model
        self._path.write_text(
            json.dumps(self._models, indent=2) + "\n", encoding="utf-8"
        )
