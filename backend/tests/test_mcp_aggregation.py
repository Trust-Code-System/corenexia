"""MCP aggregation tests (Initiative D). No network — a fake Upstream stands in for a server."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mcp import mcp_agg_router
from app.llm.base import LLMProvider, LLMResult, Message, TextBlock, ToolUseBlock
from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.mcp_aggregator import McpAggregator, UpstreamTool
from tests.test_graph import FakeSandbox


class FakeUpstream:
    def __init__(self, name: str):
        self.name = name
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[UpstreamTool]:
        return [
            UpstreamTool("search", "Search the corpus",
                         {"type": "object", "properties": {"q": {"type": "string"}}}),
            UpstreamTool("fetch", "Fetch a document", {"type": "object", "properties": {}}),
        ]

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        self.calls.append((tool_name, arguments))
        return f"{self.name}:{tool_name}:{arguments}"


# --- aggregator units ----------------------------------------------------


def test_discover_namespaces_tools():
    agg = McpAggregator([FakeUpstream("docs")])
    assert agg.discover() == 2
    assert agg.tool_names == {"docs__search", "docs__fetch"}
    specs = {s.name: s for s in agg.tool_specs()}
    assert "[via docs]" in specs["docs__search"].description
    assert specs["docs__search"].input_schema["properties"]["q"]["type"] == "string"


def test_call_routes_to_upstream():
    up = FakeUpstream("docs")
    agg = McpAggregator([up])
    agg.discover()
    content, is_error = agg.call("docs__search", {"q": "nda"})
    assert not is_error
    assert content == "docs:search:{'q': 'nda'}"
    assert up.calls == [("search", {"q": "nda"})]


def test_unknown_aggregated_tool_errors():
    agg = McpAggregator([FakeUpstream("docs")])
    agg.discover()
    content, is_error = agg.call("docs__missing", {})
    assert is_error and "unknown aggregated tool" in content


def test_one_bad_upstream_does_not_break_others():
    class Broken:
        name = "broken"

        def list_tools(self):
            raise RuntimeError("down")

        def call_tool(self, *a):
            raise RuntimeError("down")

    agg = McpAggregator([Broken(), FakeUpstream("good")])
    assert agg.discover() == 2  # only the good upstream's tools
    assert all(n.startswith("good__") for n in agg.tool_names)


# --- agent calls an aggregated tool through the graph --------------------


class UsesUpstreamToolProvider(LLMProvider):
    name = "uses-upstream"

    def __init__(self):
        self.calls = 0
        self.tool_result: str | None = None

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            assert any(t.name == "docs__search" for t in tools)  # aggregated tool is exposed
            call = ToolUseBlock(id="u1", name="docs__search", input={"q": "merger"})
            return LLMResult(Message("assistant", [call]), tool_calls=[call],
                             stop_reason="tool_use")
        self.tool_result = messages[-1].blocks[0].content
        return LLMResult(Message("assistant", [TextBlock("done")]), text="done",
                         stop_reason="end_turn")


def test_agent_calls_aggregated_tool():
    up = FakeUpstream("docs")
    agg = McpAggregator([up])
    agg.discover()
    provider = UsesUpstreamToolProvider()
    app = build_orchestrator(provider, FakeSandbox(stdout="x"), mcp_aggregator=agg)

    run_orchestration(app, "search the docs", max_iterations=4)

    assert up.calls == [("search", {"q": "merger"})]
    assert "docs:search" in provider.tool_result


# --- REST surface --------------------------------------------------------


def test_upstreams_endpoint():
    agg = McpAggregator([FakeUpstream("docs")])
    agg.discover()
    app = FastAPI()
    app.state.mcp_aggregator = agg
    app.include_router(mcp_agg_router)
    with TestClient(app) as client:
        body = client.get("/v1/mcp/upstreams").json()
        assert body["enabled"] is True
        assert body["tool_count"] == 2
        assert body["upstreams"][0]["name"] == "docs"


def test_upstreams_endpoint_disabled():
    app = FastAPI()
    app.state.mcp_aggregator = None
    app.include_router(mcp_agg_router)
    with TestClient(app) as client:
        assert client.get("/v1/mcp/upstreams").json()["enabled"] is False
