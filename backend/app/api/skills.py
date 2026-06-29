"""Reusable skills API (Initiative D).

Browse and curate the agent's saved-skill toolbox. Reads are open (catalog data); writes
(create/delete) require an API key when auth is enabled. The agent itself uses the save_skill /
load_skill tools during a run — this surface is for humans and the God View.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.auth import ApiKeyDep
from app.orchestrator.skills import InvalidSkillName

skills_router = APIRouter(prefix="/v1/skills", tags=["skills"])


class SkillView(BaseModel):
    name: str
    description: str
    code: str
    tags: list[str]
    use_count: int
    created_at: float | None = None
    updated_at: float | None = None
    last_used_at: float | None = None


class SkillSummary(BaseModel):
    name: str
    description: str
    tags: list[str]
    use_count: int


class CreateSkillRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


def _store(request: Request):
    store = getattr(request.app.state, "skills", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Skills disabled (set SKILLS_ENABLED=true).")
    return store


@skills_router.get("", response_model=list[SkillSummary])
async def list_skills(request: Request, q: str | None = None) -> list[SkillSummary]:
    """List saved skills (summaries only — no code). Optional `q` filters name/description/tags."""
    store = _store(request)
    skills = store.search(q) if q else store.list()
    return [
        SkillSummary(name=s.name, description=s.description, tags=s.tags, use_count=s.use_count)
        for s in skills
    ]


@skills_router.get("/{name}", response_model=SkillView)
async def get_skill(name: str, request: Request) -> SkillView:
    skill = _store(request).get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"No skill named '{name}'.")
    return SkillView(**vars(skill))


@skills_router.post("", response_model=SkillView, status_code=201, dependencies=[ApiKeyDep])
async def create_skill(body: CreateSkillRequest, request: Request) -> SkillView:
    try:
        skill = _store(request).save(body.name, body.description, body.code, body.tags)
    except (InvalidSkillName, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SkillView(**vars(skill))


@skills_router.delete("/{name}", status_code=204, dependencies=[ApiKeyDep])
async def delete_skill(name: str, request: Request) -> None:
    if not _store(request).delete(name):
        raise HTTPException(status_code=404, detail=f"No skill named '{name}'.")
