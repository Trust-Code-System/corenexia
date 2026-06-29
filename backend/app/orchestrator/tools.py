"""The orchestrator's tool surface. Milestone 1 ships a single tool: execute_python_code."""

from __future__ import annotations

import json

from app.llm.base import ToolSpec
from app.sandbox.base import SandboxRunner

EXECUTE_PYTHON_CODE = ToolSpec(
    name="execute_python_code",
    description=(
        "Execute a self-contained Python 3.11 script in a secure, network-isolated, ephemeral "
        "sandbox and return its stdout/stderr. There is NO internet access. Pre-installed "
        "libraries: pdfplumber, python-docx, pandas, numpy. Embed any input text directly in the "
        "script. Print results as JSON to stdout so they can be parsed."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Complete Python 3.11 source to execute. Print output to stdout.",
            }
        },
        "required": ["code"],
        "additionalProperties": False,
    },
)

# How many characters of sandbox output to feed back to the model per stream.
_MAX_OUTPUT_CHARS = 20000


def run_execute_python_code(
    tool_input: dict, sandbox: SandboxRunner, timeout: int | None = None
) -> tuple[str, bool, dict]:
    """Run the tool. Returns (tool_result_content, is_error, step_record)."""
    code = tool_input.get("code", "")
    result = sandbox.run(code, timeout=timeout)

    payload = {
        "stdout": _truncate(result.stdout),
        "stderr": _truncate(result.stderr),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
    }
    step_record = {
        "tool": EXECUTE_PYTHON_CODE.name,
        "code": code,
        **payload,
    }
    return json.dumps(payload), (not result.ok), step_record


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - _MAX_OUTPUT_CHARS} chars]"
