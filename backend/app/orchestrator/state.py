"""Shared state for the orchestration graph."""

from __future__ import annotations

from typing import Any, TypedDict

from app.llm.base import Message

DEFAULT_SYSTEM_PROMPT = (
    "You are Corenexia, an autonomous orchestrator for the legal sector (contract analysis, "
    "compliance) and general finance (equities, market analysis). You have exactly one tool: "
    "execute_python_code, which runs a self-contained Python 3.11 script in a secure, "
    "network-isolated, ephemeral sandbox (no internet access; pre-installed: pdfplumber, "
    "python-docx, pandas, numpy).\n\n"
    "When a task needs parsing, computation, or structured extraction, write a complete script "
    "and call the tool. Embed any document text you were given directly in the script. Always "
    "print the result as JSON to stdout. After you have the data, stop calling tools and write a "
    "clear final answer for the user.\n\n"
    "Stay strictly within legal and general-finance topics. Never use cryptocurrency terminology."
)


class OrchestratorState(TypedDict):
    run_id: str
    system: str
    query: str
    context: str | None
    messages: list[Message]
    iterations: int
    max_iterations: int
    status: str
    answer: str | None
    steps: list[dict[str, Any]]
    # Accumulated token/cost totals for the run (see telemetry.metering.UsageTotals.to_dict()).
    usage: dict[str, Any]
