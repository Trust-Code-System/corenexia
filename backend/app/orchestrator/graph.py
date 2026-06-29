"""The LangGraph orchestration loop.

    START → reason → (route) → execute → reason → ... → respond → END

- reason:   ask the LLM what to do next. It either calls execute_python_code or answers.
- execute:  run each requested script in the sandbox, feed results back.
- respond:  finalize the structured answer (also the landing node when the iteration cap hits).

Provider, sandbox, and the event bus are injected so the graph stays vendor-agnostic and
testable with fakes (see tests/test_graph.py).
"""

from __future__ import annotations

import uuid

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.llm.base import LLMProvider, Message, TextBlock, ToolResultBlock, ToolUseBlock
from app.orchestrator.skills import SkillStore
from app.orchestrator.state import DEFAULT_SYSTEM_PROMPT, OrchestratorState
from app.orchestrator.tools import (
    EXECUTE_PYTHON_CODE,
    LOAD_SKILL,
    REQUEST_EGRESS,
    SAVE_SKILL,
    SKILL_TOOL_NAMES,
    run_egress_tool,
    run_execute_python_code,
    run_skill_tool,
)
from app.sandbox.base import SandboxRunner
from app.sandbox.egress_approval import EgressApprovalStore
from app.telemetry import otel
from app.telemetry.events import EventBus, OrchestratorEvent, Phase
from app.telemetry.metering import UsageTotals

TOOLS = [EXECUTE_PYTHON_CODE]

_PREVIEW_CHARS = 600


def _skill_system_suffix(skills: SkillStore) -> str:
    """Append the skill catalog (names + descriptions only — progressive disclosure) + how-to."""
    suffix = (
        "\n\nReusable skills: you can save a working script as a named skill with save_skill("
        "name, description, code) and reload it later with load_skill(name) instead of rewriting "
        "it."
    )
    catalog = skills.catalog()
    if catalog:
        suffix += "\n\nSaved skills available via load_skill(name):\n" + catalog
    return suffix


def _preview(text: str) -> str:
    """Short, telemetry-safe excerpt for streaming to the UI."""
    text = text or ""
    if len(text) <= _PREVIEW_CHARS:
        return text
    return text[:_PREVIEW_CHARS] + f"\n...[+{len(text) - _PREVIEW_CHARS} chars]"


def build_orchestrator(
    provider: LLMProvider,
    sandbox: SandboxRunner,
    bus: EventBus | None = None,
    sandbox_timeout: int | None = None,
    skills: SkillStore | None = None,
    egress_approvals: EgressApprovalStore | None = None,
):
    """Compile a LangGraph app bound to the given provider/sandbox/bus.

    Optional capabilities (Initiative D), each added only when injected:
      * `skills` → save_skill/load_skill tools + a skill catalog in the system prompt,
      * `egress_approvals` → the request_egress tool (human-approval gate for outbound hosts).
    Omitting both keeps the classic single-tool behavior.
    """
    bus = bus or EventBus()
    tools = [EXECUTE_PYTHON_CODE]
    if skills:
        tools += [SAVE_SKILL, LOAD_SKILL]
    if egress_approvals:
        tools += [REQUEST_EGRESS]

    def _emit(run_id: str, phase: Phase, message: str = "", **data) -> None:
        bus.publish(OrchestratorEvent(run_id=run_id, phase=phase, message=message, data=data))

    def reason(state: OrchestratorState) -> dict:
        run_id = state["run_id"]
        _emit(run_id, Phase.THINKING, "Reasoning about the next step",
              iteration=state["iterations"])

        system = state["system"]
        if skills:
            system += _skill_system_suffix(skills)
        if egress_approvals:
            system += (
                "\n\nNetwork access: the sandbox has NO internet by default. If a task needs an "
                "outbound call, first use request_egress(host, reason); a human must approve the "
                "host before you make the call. Never assume the network is available."
            )

        request_model = getattr(provider, "_model", "") or ""
        with otel.llm_chat_span(request_model, system=provider.name) as llm_span:
            result = provider.complete(
                system=system,
                messages=state["messages"],
                tools=tools,
                max_tokens=settings.llm_max_tokens,
            )
            llm_span.record_result(
                model=result.model, usage=result.usage, finish_reason=result.stop_reason
            )

        # Fold this turn's tokens/cost into the running totals (last-write-wins state field,
        # so we read the current totals and write the updated ones).
        totals = UsageTotals.from_dict(state.get("usage")).add(result.model, result.usage)

        messages = [*state["messages"], result.assistant_message]
        update: dict = {
            "messages": messages,
            "iterations": state["iterations"] + 1,
            "usage": totals.to_dict(),
        }

        if result.tool_calls:
            first_code = str(result.tool_calls[0].input.get("code", ""))
            _emit(
                run_id,
                Phase.WRITING_CODE,
                "Generated code to run",
                tool_calls=[c.name for c in result.tool_calls],
                code_preview=_preview(first_code),
            )
            update["status"] = "executing"
        else:
            update["status"] = "done"
            update["answer"] = result.text
        return update

    def execute(state: OrchestratorState) -> dict:
        run_id = state["run_id"]
        last = state["messages"][-1]
        tool_calls = [b for b in last.blocks if isinstance(b, ToolUseBlock)]

        tool_results: list[ToolResultBlock] = []
        steps = list(state["steps"])
        for call in tool_calls:
            # Reusable-skill tools (save/load) — handled in-process, not sandbox steps.
            if skills and call.name in SKILL_TOOL_NAMES:
                content, is_error = run_skill_tool(call.name, call.input, skills)
                tool_results.append(
                    ToolResultBlock(tool_use_id=call.id, content=content, is_error=is_error)
                )
                _emit(run_id, Phase.THINKING, f"skill:{call.name}",
                      tool=call.name, is_error=is_error)
                continue

            # Egress approval gate — files a request; never opens the connection itself.
            if egress_approvals and call.name == REQUEST_EGRESS.name:
                content, is_error = run_egress_tool(call.input, egress_approvals)
                tool_results.append(
                    ToolResultBlock(tool_use_id=call.id, content=content, is_error=is_error)
                )
                _emit(run_id, Phase.THINKING, "request_egress",
                      host=call.input.get("host", ""), is_error=is_error)
                continue

            if call.name != EXECUTE_PYTHON_CODE.name:
                tool_results.append(
                    ToolResultBlock(
                        tool_use_id=call.id,
                        content=f"Unknown tool '{call.name}'.",
                        is_error=True,
                    )
                )
                continue

            _emit(run_id, Phase.EXECUTING_SANDBOX, "Executing script in sandbox",
                  status="start", tool_use_id=call.id)
            with otel.tool_span(call.name) as t_span:
                content, is_error, step = run_execute_python_code(
                    call.input, sandbox, timeout=sandbox_timeout
                )
                t_span.set_attribute("corenexia.exit_code", step["exit_code"])
                t_span.set_attribute("corenexia.timed_out", step["timed_out"])
                t_span.set_attribute("corenexia.duration_ms", step["duration_ms"])
                if is_error:
                    t_span.set_status(otel.Status(otel.StatusCode.ERROR, "tool execution failed"))
            tool_results.append(
                ToolResultBlock(tool_use_id=call.id, content=content, is_error=is_error)
            )
            steps.append(step)
            _emit(
                run_id,
                Phase.EXECUTING_SANDBOX,
                "Sandbox execution complete",
                status="complete",
                tool_use_id=call.id,
                exit_code=step["exit_code"],
                timed_out=step["timed_out"],
                duration_ms=step["duration_ms"],
                is_error=is_error,
                stdout_preview=_preview(step["stdout"]),
            )

        results_message = Message(role="user", blocks=tool_results)
        return {"messages": [*state["messages"], results_message], "steps": steps}

    def respond(state: OrchestratorState) -> dict:
        run_id = state["run_id"]
        usage = state.get("usage", {})
        if state.get("answer"):
            _emit(run_id, Phase.DONE, "Completed", iterations=state["iterations"], usage=usage)
            return {"status": "done"}

        # Landed here without a final answer => iteration cap reached with tools still pending.
        _emit(run_id, Phase.DONE, "Stopped at iteration cap",
              iterations=state["iterations"], usage=usage)
        return {
            "status": "max_iterations",
            "answer": (
                "Reached the maximum number of reasoning steps before producing a final answer. "
                "Partial results are available in `steps`."
            ),
        }

    def route(state: OrchestratorState) -> str:
        last = state["messages"][-1]
        has_tool_calls = last.role == "assistant" and any(
            isinstance(b, ToolUseBlock) for b in last.blocks
        )
        if not has_tool_calls:
            return "respond"
        if state["iterations"] >= state["max_iterations"]:
            return "respond"
        return "execute"

    graph = StateGraph(OrchestratorState)
    graph.add_node("reason", reason)
    graph.add_node("execute", execute)
    graph.add_node("respond", respond)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", route, {"execute": "execute", "respond": "respond"})
    graph.add_edge("execute", "reason")
    graph.add_edge("respond", END)
    return graph.compile()


def initial_state(query: str, context: str | None = None, *, max_iterations: int | None = None,
                  run_id: str | None = None) -> OrchestratorState:
    """Build a fresh state for one orchestration run."""
    first_user = query if not context else f"{query}\n\nContext:\n{context}"
    return OrchestratorState(
        run_id=run_id or uuid.uuid4().hex,
        system=DEFAULT_SYSTEM_PROMPT,
        query=query,
        context=context,
        messages=[Message(role="user", blocks=[TextBlock(text=first_user)])],
        iterations=0,
        max_iterations=max_iterations or settings.max_iterations,
        status="thinking",
        answer=None,
        steps=[],
        usage=UsageTotals().to_dict(),
    )


def run_orchestration(
    app, query: str, context: str | None = None, *, max_iterations: int | None = None,
    run_id: str | None = None,
) -> OrchestratorState:
    """Synchronously run a compiled orchestrator to completion and return the final state."""
    state = initial_state(query, context, max_iterations=max_iterations, run_id=run_id)
    # Allow enough graph supersteps for max_iterations reason/execute cycles plus respond.
    recursion_limit = (state["max_iterations"] * 2) + 5
    with otel.agent_run_span(state["run_id"], query) as run_span:
        final = app.invoke(state, config={"recursion_limit": recursion_limit})
        usage = final.get("usage") or {}
        run_span.set_attribute(otel.CNX_COST_USD, float(usage.get("cost_usd", 0.0)))
        run_span.set_attribute("corenexia.status", final.get("status", ""))
    return final  # type: ignore[return-value]
