"""OpenTelemetry GenAI span emission (Initiative B).

Installs an in-memory span exporter, runs the orchestrator with fakes, and asserts the
GenAI-convention spans (agent run / LLM chat / tool execution) are produced with the right
attributes and parent-child structure. No Docker, no API key, no network.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.telemetry import otel
from tests.test_graph import FakeSandbox
from tests.test_metering import UsageReportingProvider

# Install a real SDK provider once for the process so the graph's spans are captured.
_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


def test_genai_spans_emitted_with_usage_and_hierarchy():
    _exporter.clear()
    sandbox = FakeSandbox(stdout="1")
    app = build_orchestrator(UsageReportingProvider(model="claude-opus-4-8"), sandbox)

    run_orchestration(app, "Analyze this contract clause.")

    spans = _exporter.get_finished_spans()
    by_name = {s.name: s for s in spans}

    # Agent workflow span.
    assert "invoke_agent corenexia" in by_name
    agent = by_name["invoke_agent corenexia"]
    assert agent.attributes[otel.GEN_AI_OPERATION_NAME] == "invoke_agent"
    assert agent.attributes["corenexia.status"] == "done"

    # LLM chat spans carry model + token usage (GenAI semconv).
    chat_spans = [s for s in spans if s.name == "chat claude-opus-4-8"]
    assert len(chat_spans) == 2  # tool turn + final answer turn
    for s in chat_spans:
        assert s.attributes[otel.GEN_AI_OPERATION_NAME] == "chat"
        assert s.attributes[otel.GEN_AI_RESPONSE_MODEL] == "claude-opus-4-8"
        assert s.attributes[otel.GEN_AI_USAGE_INPUT_TOKENS] == 1000
        assert s.attributes[otel.GEN_AI_USAGE_OUTPUT_TOKENS] == 500

    # Tool-execution span.
    tool = by_name["execute_tool execute_python_code"]
    assert tool.attributes[otel.GEN_AI_TOOL_NAME] == "execute_python_code"
    assert tool.attributes["corenexia.exit_code"] == 0

    # Children share the agent run's trace id (one trace per run).
    assert tool.context.trace_id == agent.context.trace_id
    assert chat_spans[0].context.trace_id == agent.context.trace_id
