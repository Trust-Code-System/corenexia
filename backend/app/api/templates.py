"""Read-only template catalog (Initiative C).

`GET /v1/templates` lists ready-to-run legal/finance/general task templates; clients turn one into
an orchestration by POSTing its `query` (+ optional `example_context`) to `/v1/orchestrate`. This
is public catalog data (no secrets), so it stays open even when `AUTH_ENABLED` is on.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.templates import get_template, list_packs, list_templates

templates_router = APIRouter(prefix="/v1/templates", tags=["templates"])


class TemplateView(BaseModel):
    id: str
    title: str
    description: str
    query: str
    domain: str
    pack: str
    tags: list[str]
    example_context: str | None = None


class PackView(BaseModel):
    id: str
    domain: str
    title: str
    description: str
    template_ids: list[str]


@templates_router.get("", response_model=list[TemplateView])
async def get_templates(domain: str | None = None) -> list[TemplateView]:
    """List all templates, optionally filtered by domain (legal | finance | general)."""
    return [TemplateView(**asdict(t)) for t in list_templates(domain)]


@templates_router.get("/packs", response_model=list[PackView])
async def get_packs() -> list[PackView]:
    """List the template packs (without inlining every template)."""
    return [
        PackView(
            id=p.id,
            domain=p.domain,
            title=p.title,
            description=p.description,
            template_ids=[t.id for t in p.templates],
        )
        for p in list_packs()
    ]


@templates_router.get("/{template_id}", response_model=TemplateView)
async def get_one_template(template_id: str) -> TemplateView:
    tpl = get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"No template with id '{template_id}'.")
    return TemplateView(**asdict(tpl))
