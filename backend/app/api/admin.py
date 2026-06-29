"""Admin API for key management. Guarded by ADMIN_TOKEN (header: X-Admin-Token)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.auth import require_admin

admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class KeyView(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: float
    revoked: bool
    request_count: int
    last_used_at: float | None
    # Metering (Initiative B)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    spend_cap_usd: float | None = None


class SpendCapRequest(BaseModel):
    # USD cap; null clears it (unlimited).
    spend_cap_usd: float | None = Field(None, ge=0)


class CreateKeyResponse(BaseModel):
    id: str
    name: str
    # The full key — shown ONCE. Store it now; it cannot be retrieved again.
    api_key: str
    prefix: str
    created_at: float


@admin_router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(body: CreateKeyRequest, request: Request) -> CreateKeyResponse:
    raw, record = request.app.state.keys.create(body.name)
    return CreateKeyResponse(
        id=record.id,
        name=record.name,
        api_key=raw,
        prefix=record.prefix,
        created_at=record.created_at,
    )


@admin_router.get("/keys", response_model=list[KeyView])
async def list_keys(request: Request) -> list[KeyView]:
    return [KeyView(**vars(r)) for r in request.app.state.keys.list()]


@admin_router.put("/keys/{key_id}/spend-cap", response_model=KeyView)
async def set_spend_cap(key_id: str, body: SpendCapRequest, request: Request) -> KeyView:
    if not request.app.state.keys.set_spend_cap(key_id, body.spend_cap_usd):
        raise HTTPException(status_code=404, detail=f"No key with id '{key_id}'.")
    return KeyView(**vars(request.app.state.keys.get(key_id)))


@admin_router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request) -> None:
    if not request.app.state.keys.revoke(key_id):
        raise HTTPException(status_code=404, detail=f"No active key with id '{key_id}'.")
