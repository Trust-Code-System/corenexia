"""Graph tests with fakes — no Docker, no API key, no network.

Verifies the reason -> execute -> respond path and the iteration cap by injecting a scripted
LLMProvider and a canned SandboxRunner.
"""

from __future__ import annotations

import json

from app.llm.base import (
    LLMProvider,
    LLMResult,
    Message,
    TextBlock,
    ToolUseBlock,
)
from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.tools import EXECUTE_PYTHON_CODE
from app.sandbox.base import SandboxResult, SandboxRunner


class FakeSandbox(SandboxRunner):
    def __init__(self, stdout: str):
        self._stdout = stdout
        self.calls: list[str] = []

    def run(self, code, files=None, timeout=None) -> SandboxResult:
        self.calls.append(code)
        return SandboxResult(
            stdout=self._stdout, stderr="", exit_code=0, timed_out=False, duration_ms=5
        )


class ScriptedProvider(LLMProvider):
    """Calls the tool once, then returns a final answer."""

    name = "scripted"

    def __init__(self):
        self.call_count = 0

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.call_count += 1
        if self.call_count == 1:
            call = ToolUseBlock(
                id="tool_1",
                name=EXECUTE_PYTHON_CODE.name,
                input={"code": "print('{\"governing_law\": \"Delaware\"}')"},
            )
            return LLMResult(
                assistant_message=Message(role="assistant", blocks=[call]),
                tool_calls=[call],
                text="",
                stop_reason="tool_use",
            )
        final = "Governing law is Delaware."
        return LLMResult(
            assistant_message=Message(role="assistant", blocks=[TextBlock(text=final)]),
            tool_calls=[],
            text=final,
            stop_reason="end_turn",
        )


class AlwaysToolProvider(LLMProvider):
    """Never stops calling the tool — exercises the iteration cap."""

    name = "always-tool"

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        call = ToolUseBlock(
            id="loop", name=EXECUTE_PYTHON_CODE.name, input={"code": "print(1)"}
        )
        return LLMResult(
            assistant_message=Message(role="assistant", blocks=[call]),
            tool_calls=[call],
            text="",
            stop_reason="tool_use",
        )


def test_reason_execute_respond_path():
    sandbox = FakeSandbox(stdout='{"governing_law": "Delaware"}')
    app = build_orchestrator(provider=ScriptedProvider(), sandbox=sandbox)

    final = run_orchestration(app, "What is the governing law?")

    assert final["status"] == "done"
    assert final["answer"] == "Governing law is Delaware."
    assert len(sandbox.calls) == 1
    assert len(final["steps"]) == 1
    step = final["steps"][0]
    assert step["tool"] == EXECUTE_PYTHON_CODE.name
    assert json.loads(step["stdout"])["governing_law"] == "Delaware"


def test_iteration_cap_stops_runaway_loop():
    sandbox = FakeSandbox(stdout="1")
    app = build_orchestrator(provider=AlwaysToolProvider(), sandbox=sandbox)

    final = run_orchestration(app, "Loop forever", max_iterations=3)

    assert final["status"] == "max_iterations"
    assert final["iterations"] == 3
    # reason runs 3 times (0->1->2->3); the 3rd hits the cap and routes to respond, so the
    # sandbox executed after only the first two reasoning steps.
    assert len(sandbox.calls) == 2
