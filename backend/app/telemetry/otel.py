"""OpenTelemetry tracing with GenAI semantic conventions.

Corenexia emits OTel spans for the agent's work so any OTLP-compatible backend — **Langfuse**,
**Arize Phoenix**, Jaeger, Grafana Tempo, Honeycomb, etc. — can ingest them with zero vendor
lock-in (see OBSERVABILITY.md). We follow the OpenTelemetry *GenAI* semantic conventions:

  * an `invoke_agent corenexia` span per orchestration run (the workflow),
  * a `chat {model}` span per LLM turn (model + token-usage attributes),
  * an `execute_tool execute_python_code` span per sandbox execution.

Tracing is **off by default**. `setup_tracing()` (called from the app lifespan) installs an SDK
TracerProvider only when `settings.otel_enabled` is true; otherwise every helper here resolves to
the OpenTelemetry *no-op* tracer, so the orchestrator — and the test suite — run unchanged with no
spans and no dependencies exercised.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from app.llm.base import Usage

logger = logging.getLogger("corenexia.otel")

# --- GenAI semantic-convention attribute keys (opentelemetry.io/.../gen-ai) ---
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
# Corenexia-specific extras (namespaced so they never collide with the spec).
CNX_RUN_ID = "corenexia.run_id"
CNX_COST_USD = "corenexia.cost_usd"

_TRACER_NAME = "corenexia.orchestrator"
_configured = False


def setup_tracing(settings) -> bool:
    """Install an SDK TracerProvider when enabled. Idempotent. Returns True if tracing is active.

    Exporter selection (when `otel_enabled`):
      * if `OTEL_EXPORTER_OTLP_ENDPOINT` is set → OTLP/HTTP exporter (Langfuse/Phoenix/Jaeger/…),
      * else if `otel_console_export` → console exporter (local debugging),
      * else → provider installed but no exporter (warns; spans are dropped).
    The OTLP exporter reads endpoint/headers from the standard `OTEL_EXPORTER_OTLP_*` env vars.
    """
    global _configured
    if _configured or not getattr(settings, "otel_enabled", False):
        return _configured

    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create(
            {"service.name": getattr(settings, "otel_service_name", "corenexia")}
        )
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
        )
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            logger.info("OTel tracing → OTLP exporter (%s)", endpoint)
        elif getattr(settings, "otel_console_export", False):
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OTel tracing → console exporter")
        else:
            logger.warning(
                "OTEL_ENABLED is set but no exporter configured "
                "(set OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_CONSOLE_EXPORT); spans will be dropped."
            )

        trace.set_tracer_provider(provider)
        _configured = True
        logger.info("OpenTelemetry tracing enabled (service=%s).", resource.attributes)
    except Exception:  # never let observability wiring break startup
        logger.exception("Failed to set up OpenTelemetry tracing; continuing without it.")
    return _configured


def _tracer():
    return trace.get_tracer(_TRACER_NAME)


def _set_usage(span: Span, usage: Usage | None) -> None:
    if usage is None:
        return
    span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, usage.input_tokens)
    span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, usage.output_tokens)


@contextmanager
def agent_run_span(run_id: str, query: str, agent: str = "corenexia") -> Iterator[Span]:
    """Workflow span covering one orchestration run."""
    with _tracer().start_as_current_span(f"invoke_agent {agent}") as span:
        span.set_attribute(GEN_AI_OPERATION_NAME, "invoke_agent")
        span.set_attribute(GEN_AI_SYSTEM, "corenexia")
        span.set_attribute(GEN_AI_AGENT_NAME, agent)
        span.set_attribute(CNX_RUN_ID, run_id)
        try:
            yield span
        except Exception as exc:  # noqa: BLE001 — record then re-raise
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


@contextmanager
def llm_chat_span(request_model: str, system: str = "anthropic") -> Iterator[LLMSpan]:
    """LLM turn span. The caller sets the result via the yielded handle."""
    name = f"chat {request_model}" if request_model else "chat"
    with _tracer().start_as_current_span(name) as span:
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        span.set_attribute(GEN_AI_SYSTEM, system)
        if request_model:
            span.set_attribute(GEN_AI_REQUEST_MODEL, request_model)
        handle = LLMSpan(span)
        try:
            yield handle
        except Exception as exc:  # noqa: BLE001
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


class LLMSpan:
    """Small handle so the graph can record the LLM result onto its span."""

    def __init__(self, span: Span):
        self._span = span

    def record_result(self, *, model: str, usage: Usage | None, finish_reason: str = "") -> None:
        if model:
            self._span.set_attribute(GEN_AI_RESPONSE_MODEL, model)
        if finish_reason:
            self._span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason])
        _set_usage(self._span, usage)


@contextmanager
def tool_span(tool_name: str) -> Iterator[Span]:
    """Tool-execution span (one sandbox run)."""
    with _tracer().start_as_current_span(f"execute_tool {tool_name}") as span:
        span.set_attribute(GEN_AI_OPERATION_NAME, "execute_tool")
        span.set_attribute(GEN_AI_TOOL_NAME, tool_name)
        try:
            yield span
        except Exception as exc:  # noqa: BLE001
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
