"""MCP server surface — exposes the orchestrator as a Model Context Protocol tool.

External MCP clients (Claude Desktop, IDEs, other agents) connect to `/mcp` (streamable HTTP)
and call the `orchestrate` tool, inheriting the full dynamic reasoning engine. The compiled
orchestrator is injected by the FastAPI lifespan via `engine.orchestrator` so this module shares
the same provider/sandbox as the REST gateway.

Stateless HTTP keeps the surface simple to scale. The session manager is run inside the FastAPI
lifespan (see app/main.py).
"""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from app.orchestrator.graph import run_orchestration

mcp = FastMCP("corenexia_mcp", stateless_http=True, streamable_http_path="/")


class _Engine:
    """Holder for the compiled orchestrator, populated by the FastAPI lifespan."""

    orchestrator = None


engine = _Engine()


class OrchestrateInput(BaseModel):
    """Input for the orchestrate tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="The legal or general-finance task to perform "
        "(e.g. 'Extract the governing law and termination notice period from this contract').",
        min_length=1,
        max_length=8000,
    )
    context: str | None = Field(
        default=None,
        description="Optional supporting text such as a contract excerpt or dataset.",
        max_length=200000,
    )
    max_iterations: int | None = Field(
        default=None,
        description="Optional cap on orchestrator reasoning steps (1-20).",
        ge=1,
        le=20,
    )


@mcp.tool(
    name="orchestrate",
    annotations={
        "title": "Corenexia Dynamic Orchestrator",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def orchestrate(params: OrchestrateInput) -> str:
    """Run a legal/finance task through the Corenexia orchestrator.

    The orchestrator reasons about the task, writes Python on demand, and runs it in a secure,
    network-isolated, ephemeral sandbox, then returns a structured answer. Use for contract
    analysis, compliance checks, and general-finance computations. Not for cryptocurrency.

    Args:
        params (OrchestrateInput): query, optional context, optional max_iterations.

    Returns:
        str: JSON with schema:
        {
            "run_id": str,
            "status": str,          # "done" | "max_iterations" | "error"
            "answer": str | null,   # the final answer
            "iterations": int,
            "steps": [              # one entry per sandbox execution
                {"tool": str, "exit_code": int, "timed_out": bool, "duration_ms": int}
            ]
        }
        On failure: "Error: <message>".
    """
    if engine.orchestrator is None:
        return "Error: orchestrator not initialized."
    try:
        final = await asyncio.to_thread(
            run_orchestration,
            engine.orchestrator,
            params.query,
            params.context,
            max_iterations=params.max_iterations,
        )
    except Exception as exc:  # noqa: BLE001 — return an actionable message to the agent
        return f"Error: orchestration failed: {exc}"

    return json.dumps(
        {
            "run_id": final["run_id"],
            "status": final["status"],
            "answer": final["answer"],
            "iterations": final["iterations"],
            "steps": [
                {
                    "tool": s["tool"],
                    "exit_code": s["exit_code"],
                    "timed_out": s["timed_out"],
                    "duration_ms": s["duration_ms"],
                }
                for s in final["steps"]
            ],
        },
        indent=2,
    )
