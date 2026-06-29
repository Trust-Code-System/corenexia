"""True MCP aggregation (Initiative D).

Corenexia can connect to **upstream** MCP servers, discover their tools, and re-expose them to the
orchestrator under namespaced names (``<upstream>__<tool>``). The agent can then call an upstream
tool just like a first-party one; the aggregator routes the call to the right server.

Design for testability: an `Upstream` is anything with `name`, `list_tools()`, and
`call_tool(name, args)`. The production adapter (`StreamableHttpUpstream`) speaks MCP over
streamable HTTP via the official SDK, bridging its async client to our synchronous graph. Tests
inject a fake `Upstream`, so namespacing/routing/dispatch are verified without any network.

Security note: upstream tools are *untrusted third-party metadata*. We namespace them and pass
their declarations through, but per SECURITY.md the orchestrator must not treat upstream tool
descriptions as privileged instructions — keep the system prompt first-party.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app.llm.base import ToolSpec

logger = logging.getLogger("corenexia.mcp_aggregator")

_NAMESPACE_SEP = "__"


@dataclass
class UpstreamTool:
    name: str
    description: str
    input_schema: dict


class Upstream(Protocol):
    name: str

    def list_tools(self) -> list[UpstreamTool]: ...

    def call_tool(self, tool_name: str, arguments: dict) -> str: ...


@dataclass
class UpstreamSpec:
    name: str
    url: str
    auth_header: str | None = None  # full "Authorization" value, if the upstream needs one


class McpAggregator:
    """Holds upstreams, exposes their tools namespaced, and routes calls back to them."""

    def __init__(self, upstreams: list[Upstream] | None = None):
        self._upstreams: dict[str, Upstream] = {}
        self._tools: dict[str, tuple[str, str]] = {}  # namespaced -> (upstream, raw tool name)
        self._specs: list[ToolSpec] = []
        for up in upstreams or []:
            self.add(up)

    def add(self, upstream: Upstream) -> None:
        self._upstreams[upstream.name] = upstream

    def discover(self) -> int:
        """(Re)load tools from every upstream. Returns the number of aggregated tools."""
        self._tools.clear()
        self._specs.clear()
        for name, up in self._upstreams.items():
            try:
                tools = up.list_tools()
            except Exception as exc:  # noqa: BLE001 — one bad upstream must not break the rest
                logger.warning("upstream '%s' tool discovery failed: %s", name, exc)
                continue
            for tool in tools:
                namespaced = f"{name}{_NAMESPACE_SEP}{tool.name}"
                self._tools[namespaced] = (name, tool.name)
                self._specs.append(
                    ToolSpec(
                        name=namespaced,
                        description=f"[via {name}] {tool.description}",
                        input_schema=tool.input_schema or {"type": "object", "properties": {}},
                    )
                )
        logger.info("MCP aggregation: %d tools from %d upstream(s)",
                    len(self._specs), len(self._upstreams))
        return len(self._specs)

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    def tool_specs(self) -> list[ToolSpec]:
        return list(self._specs)

    def is_aggregated(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def call(self, namespaced_name: str, arguments: dict) -> tuple[str, bool]:
        """Route a namespaced tool call to its upstream. Returns (content, is_error)."""
        route = self._tools.get(namespaced_name)
        if route is None:
            return json.dumps({"error": f"unknown aggregated tool '{namespaced_name}'"}), True
        upstream_name, raw_name = route
        up = self._upstreams[upstream_name]
        try:
            return up.call_tool(raw_name, arguments), False
        except Exception as exc:  # noqa: BLE001 — surface as a tool error to the agent
            return json.dumps({"error": f"upstream '{upstream_name}' call failed: {exc}"}), True

    def describe(self) -> list[dict]:
        """Summary for the REST surface: upstreams and their (namespaced) tools."""
        out: list[dict] = []
        for name in self._upstreams:
            tools = [ns for ns, (up, _) in self._tools.items() if up == name]
            out.append({"name": name, "tools": sorted(tools)})
        return out


class StreamableHttpUpstream:
    """Production `Upstream` adapter: an MCP server reachable over streamable HTTP.

    Each method opens a short-lived MCP session (connect → call → close), which suits stateless
    streamable-HTTP servers and avoids holding connections across the sync/async boundary. The
    async SDK client is driven with `asyncio.run`, so this must be called from a thread with no
    running event loop (the orchestrator graph runs in a worker thread — see runs.py).
    """

    def __init__(self, spec: UpstreamSpec):
        self.name = spec.name
        self._url = spec.url
        self._headers = {"Authorization": spec.auth_header} if spec.auth_header else None

    def list_tools(self) -> list[UpstreamTool]:
        return asyncio.run(self._list_tools())

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        return asyncio.run(self._call_tool(tool_name, arguments))

    async def _session(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        return streamablehttp_client(self._url, headers=self._headers), ClientSession

    async def _list_tools(self) -> list[UpstreamTool]:
        ctx, ClientSession = await self._session()
        async with ctx as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [
                UpstreamTool(
                    name=t.name,
                    description=t.description or "",
                    input_schema=dict(t.inputSchema or {}),
                )
                for t in resp.tools
            ]

    async def _call_tool(self, tool_name: str, arguments: dict) -> str:
        ctx, ClientSession = await self._session()
        async with ctx as (read, write, _), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            parts = [getattr(c, "text", "") for c in (result.content or [])]
            return "\n".join(p for p in parts if p) or "(no content)"
