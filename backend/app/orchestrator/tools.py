"""The orchestrator's tool surface.

`execute_python_code` is the core tool. When a `SkillStore` is wired in (Initiative D), two more
tools let the agent build a reusable toolbox: `save_skill` (persist working code under a name) and
`load_skill` (pull a saved skill's code on demand — progressive disclosure).
"""

from __future__ import annotations

import json

from app.llm.base import ToolSpec
from app.orchestrator.skills import InvalidSkillName, SkillStore
from app.sandbox.base import SandboxRunner
from app.sandbox.egress_approval import EgressApprovalStore

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


# --- Reusable skills (Initiative D) --------------------------------------

SAVE_SKILL = ToolSpec(
    name="save_skill",
    description=(
        "Save a working, self-contained Python script as a named, reusable skill so you can reuse "
        "it later instead of rewriting it. Use after a script succeeds and is likely useful again."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique skill name ([a-zA-Z0-9_.-], <=64)."},
            "description": {"type": "string", "description": "One line: what the skill does."},
            "code": {"type": "string", "description": "The complete Python 3.11 source to save."},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "description", "code"],
        "additionalProperties": False,
    },
)

LOAD_SKILL = ToolSpec(
    name="load_skill",
    description=(
        "Load the full Python source of a previously saved skill by name (the catalog of available "
        "skills is in your system prompt). Then run or adapt it with execute_python_code."
    ),
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "The saved skill's name."}},
        "required": ["name"],
        "additionalProperties": False,
    },
)

SKILL_TOOL_NAMES = {SAVE_SKILL.name, LOAD_SKILL.name}


def run_skill_tool(tool_name: str, tool_input: dict, skills: SkillStore) -> tuple[str, bool]:
    """Handle a skill tool call. Returns (tool_result_content, is_error)."""
    if tool_name == SAVE_SKILL.name:
        try:
            skill = skills.save(
                tool_input.get("name", ""),
                tool_input.get("description", ""),
                tool_input.get("code", ""),
                tool_input.get("tags") or [],
            )
        except (InvalidSkillName, ValueError) as exc:
            return f"Could not save skill: {exc}", True
        return json.dumps({"saved": skill.name, "status": "ok"}), False

    if tool_name == LOAD_SKILL.name:
        skill = skills.get(tool_input.get("name", ""))
        if skill is None:
            return json.dumps({"error": "skill not found"}), True
        skills.record_use(skill.name)
        return json.dumps(
            {"name": skill.name, "description": skill.description, "code": skill.code}
        ), False

    return f"Unknown skill tool '{tool_name}'.", True


# --- Dynamic integration synthesis: human-approval gate (Initiative D) ----

REQUEST_EGRESS = ToolSpec(
    name="request_egress",
    description=(
        "Request permission to make outbound network calls to a specific host (e.g. to use a "
        "synthesized API client). The sandbox has NO network unless a host is approved by a human. "
        "This does NOT grant access immediately — it files a request a person must approve. Use it "
        "before writing code that needs the internet, then proceed only once the host is approved."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Hostname to reach, e.g. api.example.com."},
            "reason": {"type": "string", "description": "Why this outbound call is needed."},
        },
        "required": ["host", "reason"],
        "additionalProperties": False,
    },
)


def run_egress_tool(tool_input: dict, approvals: EgressApprovalStore) -> tuple[str, bool]:
    """Handle a request_egress call. Returns (tool_result_content, is_error)."""
    try:
        req = approvals.request(tool_input.get("host", ""), tool_input.get("reason", ""))
    except ValueError as exc:
        return f"Could not request egress: {exc}", True
    if req.status == "approved":
        return json.dumps({"host": req.host, "status": "allowed",
                           "note": "Host already permitted; you may make the call."}), False
    return json.dumps({"host": req.host, "status": "pending_approval", "request_id": req.id,
                       "note": "A human must approve this host before any outbound call."}), False
