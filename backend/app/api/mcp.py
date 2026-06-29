"""Read-only view of aggregated upstream MCP servers (Initiative D).

`GET /v1/mcp/upstreams` lists the upstream MCP servers Corenexia has connected to and the
namespaced tools it re-exposes to the orchestrator. Public catalog data.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

mcp_agg_router = APIRouter(prefix="/v1/mcp", tags=["mcp-aggregation"])


@mcp_agg_router.get("/upstreams")
async def list_upstreams(request: Request) -> dict:
    agg = getattr(request.app.state, "mcp_aggregator", None)
    if agg is None:
        return {"enabled": False, "upstreams": []}
    return {"enabled": True, "upstreams": agg.describe(), "tool_count": len(agg.tool_names)}
