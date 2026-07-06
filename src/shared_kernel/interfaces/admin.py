"""Admin endpoints: runtime model configuration.

PATCH /admin/model-config swaps a provider's default model without a deploy.
Guarded by the SECRET_KEY shared secret (X-Admin-Token header).
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from ..llm.factory import PROVIDERS

router = APIRouter(prefix="/admin", tags=["admin"])


class ModelConfigPatch(BaseModel):
    provider: str
    model: str


@router.get("/model-config")
def get_model_config(request: Request, x_admin_token: str | None = Header(None)):
    _authorize(request, x_admin_token)
    return request.app.state.model_config_store.all_models()


@router.patch("/model-config")
def patch_model_config(
    patch: ModelConfigPatch,
    request: Request,
    x_admin_token: str | None = Header(None),
):
    _authorize(request, x_admin_token)
    if patch.provider not in PROVIDERS:
        valid = ", ".join(sorted(PROVIDERS))
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider {patch.provider!r}; expected one of: {valid}",
        )
    store = request.app.state.model_config_store
    store.set_default(patch.provider, patch.model)
    return store.all_models()


def _authorize(request: Request, token: str | None) -> None:
    secret = request.app.state.settings.secret_key
    if not secret:
        raise HTTPException(
            status_code=503, detail="Admin API disabled: SECRET_KEY is not set."
        )
    if token != secret:
        raise HTTPException(status_code=401, detail="Invalid admin token.")
