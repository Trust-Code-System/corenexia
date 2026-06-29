# Observability & Evals

Corenexia is **OpenTelemetry-native**. The orchestrator emits spans following the OpenTelemetry
**GenAI semantic conventions**, so you can plug it into any OTLP-compatible backend — **Langfuse**,
**Arize Phoenix**, Jaeger, Grafana Tempo, Honeycomb, Datadog — without vendor lock-in. It also
meters **tokens and cost** per run and per API key, and ships an **eval harness** with a CI gate.

---

## 1. Tracing (OpenTelemetry GenAI spans)

### What gets emitted

Every orchestration run produces one trace:

```
invoke_agent corenexia                 (gen_ai.operation.name=invoke_agent, corenexia.run_id, corenexia.cost_usd)
├─ chat claude-opus-4-8                 (gen_ai.operation.name=chat, gen_ai.request/response.model,
│                                        gen_ai.usage.input_tokens, gen_ai.usage.output_tokens)
├─ execute_tool execute_python_code     (gen_ai.tool.name, corenexia.exit_code, corenexia.duration_ms)
├─ chat claude-opus-4-8
└─ ...
```

Attribute keys are the GenAI standard (`gen_ai.*`); Corenexia-specific extras are namespaced
under `corenexia.*` so they never collide with the spec. Implementation: `app/telemetry/otel.py`,
emitted from `app/orchestrator/graph.py`.

### Turning it on

Tracing is **off by default** (zero overhead, no spans). Enable it and point it at a collector
via the standard OTel environment variables:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=corenexia
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces   # OTLP/HTTP
# OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<token>   # if the backend needs auth
```

For a quick local look without any collector, print spans to stdout instead:

```bash
OTEL_ENABLED=true
OTEL_CONSOLE_EXPORT=true
```

### Langfuse (open source, self-hostable or cloud)

Langfuse ingests OpenTelemetry directly. Point the exporter at its OTLP endpoint and pass your
project keys as a Basic auth header (`base64("public_key:secret_key")`):

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(pk:sk)>
```

(For self-hosted Langfuse, swap the host for your instance. Header values are URL-encoded:
`%20` is a space.)

### Arize Phoenix (open source)

Run Phoenix locally (`pip install arize-phoenix && phoenix serve`, listens on `:6006`), then:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces
```

Open `http://localhost:6006` to see each run as a trace with the LLM and tool spans nested
under it, including token counts and latency.

---

## 2. Token + cost metering

Every model turn reports token usage (`LLMResult.usage`); the graph accumulates it across a run
and prices it with a per-model table (`app/telemetry/metering.py`).

- **Per run:** the `usage` block is returned on `POST /v1/orchestrate`, included in the
  `done` telemetry event, persisted with the run record, and set as `corenexia.cost_usd` on the
  trace.

  ```json
  "usage": {
    "input_tokens": 8421, "output_tokens": 1290, "total_tokens": 9711,
    "cost_usd": 0.074155, "llm_calls": 3
  }
  ```

- **Per key:** each finished run's tokens/cost are metered onto the API key that paid for it.
  See them in the admin listing (`GET /admin/keys`): `input_tokens`, `output_tokens`, `cost_usd`.

- **Spend caps:** set a per-key USD cap; once a key's accumulated `cost_usd` reaches it, new
  orchestration requests are rejected with **HTTP 402**. Reads (`GET /v1/runs/{id}`) are never
  blocked.

  ```bash
  curl -X PUT localhost:8000/admin/keys/<id>/spend-cap \
    -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' \
    -d '{"spend_cap_usd": 25.00}'      # null clears the cap (unlimited)
  ```

### Keeping prices current

The built-in price table is approximate (USD per million tokens). Override it without a code
change via `CORENEXIA_MODEL_PRICES` (JSON):

```bash
CORENEXIA_MODEL_PRICES='{"claude-opus-4-8": {"input": 5.0, "output": 25.0}}'
```

Unknown models meter at `$0` and log a one-time warning — metering never crashes a run.

---

## 3. Eval harness (CI gate)

`backend/evals/` holds a curated **legal + finance** task dataset, reusable evaluators, and a
runner that scores results against thresholds. See `backend/evals/README.md` for details. In
short:

```bash
# Deterministic gate — no LLM cost, no API key. Runs in CI.
python -m evals.run --offline

# Live evaluation against the real model (spends money; user-gated).
python -m evals.run --live
```

The offline gate replays canned code/answers through the **real Docker sandbox** and scores the
outputs deterministically, so a regression in the orchestration/execution path or the evaluators
fails CI without any paid API call. The same dataset and evaluators run against the live model
when you opt in.
