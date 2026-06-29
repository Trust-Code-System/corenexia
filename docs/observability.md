# Observability & evals

Corenexia is OpenTelemetry-native and meters tokens + cost per run and per key. The complete guide
— exporter setup for Langfuse/Phoenix, the cost table, spend caps, and the eval harness — is in
**[../OBSERVABILITY.md](../OBSERVABILITY.md)**. This page is a summary.

## Tracing (OpenTelemetry GenAI spans)

Each run emits one trace following the GenAI semantic conventions:

```text
invoke_agent corenexia
├─ chat <model>                 gen_ai.usage.input_tokens / output_tokens, request/response model
├─ execute_tool execute_python_code   corenexia.exit_code / duration_ms
└─ …
```

Off by default. Turn it on and point it anywhere that speaks OTLP:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces     # Phoenix
# or Langfuse cloud:
# OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces
# OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(pk:sk)>
# debug only: OTEL_CONSOLE_EXPORT=true
```

Works with Langfuse, Arize Phoenix, Jaeger, Grafana Tempo, Honeycomb, Datadog — no vendor lock-in.

## Token + cost metering

- **Per run** — `usage` is returned on `/v1/orchestrate`, included in the `done` telemetry event,
  persisted with the run, set as `corenexia.cost_usd` on the trace, and shown in the God View.
- **Per key** — each run's tokens/cost are metered onto the API key (`GET /admin/keys`).
- **Spend caps** — `PUT /admin/keys/{id}/spend-cap`; new requests get **402** once a key reaches its
  cap. Override prices with `CORENEXIA_MODEL_PRICES` (JSON, USD per million tokens).

## Eval harness (CI gate)

`backend/evals/` holds a legal + finance dataset, reusable evaluators, and a runner:

```bash
cd backend
python -m evals.run --offline    # deterministic gate — fixtures + real sandbox, no LLM cost (CI)
python -m evals.run --live       # real model (spends money; user-gated)
```

The offline gate replays canned code/answers through the real Docker sandbox and scores them
deterministically, so a regression fails CI without any paid API call. Details and how to add tasks:
[../backend/evals/README.md](../backend/evals/README.md).
