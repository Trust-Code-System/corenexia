"""Deterministic fixture provider for the offline eval gate.

`FixtureProvider` replays a task's canned tool code on the first turn and its canned final answer
on the second — no LLM call, no API key. The code still runs in the **real Docker sandbox**, so
the offline gate genuinely exercises code execution + the evaluators, just without paying for a
model. The same dataset runs against the live model via `evals.run --live`.
"""

from __future__ import annotations

from app.llm.base import (
    LLMProvider,
    LLMResult,
    Message,
    TextBlock,
    ToolUseBlock,
    Usage,
)
from app.orchestrator.tools import EXECUTE_PYTHON_CODE


class FixtureProvider(LLMProvider):
    name = "eval-fixture"

    def __init__(self, code: str, answer: str):
        self._code = code
        self._answer = answer
        self.call_count = 0

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.call_count += 1
        # Zero usage — offline runs are free; cost assertions stay at $0.
        usage = Usage()
        if self.call_count == 1:
            call = ToolUseBlock(
                id="fixture_1", name=EXECUTE_PYTHON_CODE.name, input={"code": self._code}
            )
            return LLMResult(
                assistant_message=Message(role="assistant", blocks=[call]),
                tool_calls=[call], text="", stop_reason="tool_use", usage=usage,
            )
        return LLMResult(
            assistant_message=Message(role="assistant", blocks=[TextBlock(text=self._answer)]),
            tool_calls=[], text=self._answer, stop_reason="end_turn", usage=usage,
        )
