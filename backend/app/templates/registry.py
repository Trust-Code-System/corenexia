"""Loads template packs from JSON and exposes a tiny read-only API.

Packs live in `packs/*.json`. They're loaded once at import and validated into dataclasses so a
malformed pack fails fast and loudly rather than at request time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_PACKS_DIR = Path(__file__).parent / "packs"


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    description: str
    query: str
    domain: str
    pack: str
    tags: list[str] = field(default_factory=list)
    example_context: str | None = None


@dataclass(frozen=True)
class TemplatePack:
    id: str
    domain: str
    title: str
    description: str
    templates: list[Template]


def _load_pack(path: Path) -> TemplatePack:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pack_id = raw["id"]
    domain = raw["domain"]
    templates = [
        Template(
            id=t["id"],
            title=t["title"],
            description=t["description"],
            query=t["query"],
            domain=domain,
            pack=pack_id,
            tags=list(t.get("tags", [])),
            example_context=t.get("example_context"),
        )
        for t in raw["templates"]
    ]
    return TemplatePack(
        id=pack_id,
        domain=domain,
        title=raw["title"],
        description=raw["description"],
        templates=templates,
    )


@lru_cache(maxsize=1)
def _packs() -> list[TemplatePack]:
    packs = [_load_pack(p) for p in sorted(_PACKS_DIR.glob("*.json"))]
    # Guard against duplicate template ids across packs (they must be globally unique).
    seen: set[str] = set()
    for pack in packs:
        for tpl in pack.templates:
            if tpl.id in seen:
                raise ValueError(f"Duplicate template id across packs: {tpl.id!r}")
            seen.add(tpl.id)
    return packs


def list_packs() -> list[TemplatePack]:
    return list(_packs())


def list_templates(domain: str | None = None) -> list[Template]:
    out: list[Template] = []
    for pack in _packs():
        if domain and pack.domain != domain:
            continue
        out.extend(pack.templates)
    return out


def get_template(template_id: str) -> Template | None:
    for tpl in list_templates():
        if tpl.id == template_id:
            return tpl
    return None
