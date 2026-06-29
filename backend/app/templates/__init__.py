"""Template/skill packs (Initiative C).

Flagship **legal** and **finance** packs plus a domain-neutral **general** starter, demonstrating
the "general engine + vertical templates" direction. Packs are static JSON discovery data exposed
read-only at `GET /v1/templates`; clients (and the God View) turn a template into a normal
orchestration request by POSTing its `query` (+ optional `example_context`).
"""

from app.templates.registry import (
    Template,
    TemplatePack,
    get_template,
    list_packs,
    list_templates,
)

__all__ = [
    "Template",
    "TemplatePack",
    "get_template",
    "list_packs",
    "list_templates",
]
