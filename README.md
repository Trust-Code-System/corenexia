# Corenexia

**The open, self-hostable Infinite Dynamic Orchestrator.** When the agent lacks a pre-built tool,
it **writes Python on the fly and runs it in a hardened, ephemeral sandbox**, then returns
structured results — with a visual "God View", a REST + MCP gateway, OpenTelemetry tracing, and
token/cost metering.

> Flagship domains: **legal** (contract analysis, NDA triage, compliance) and **general finance**
> (equities, valuation, portfolio math). General-purpose engine underneath. No cryptocurrency.

```text
┌── God View (Next.js + React Flow) ──┐      live telemetry over WebSocket
│  thinking → writing_code → sandbox  │◀───────────────────────────────┐
└──────────────┬──────────────────────┘                                │
               │ REST / MCP                                            │
        ┌──────▼───────────────────────────────────────────────┐      │
        │  FastAPI gateway   /v1/*   /mcp   /admin   /v1/templates│     │
        │  LangGraph loop:  reason ──▶ execute ──▶ (loop) ──▶ respond────┘
        │                     │            │
        │              LLMProvider     SandboxRunner
        │              (Claude;         (hardened Docker | gVisor | E2B)
        │               Gemini stub)         │
        └─────────────────────────────────────▼─────────────────┐
                       one ephemeral, network-isolated container per run
```

## Why Corenexia

MCP gateways route *existing* tools; agent builders are visual/deterministic; sandbox vendors give
isolation but no orchestration. **Corenexia unifies dynamic code-gen orchestration + an MCP gateway
+ visual observability in one open, self-hostable product** — the "code execution with MCP" pattern,
productized, security-first.

## Features

- **Dynamic code orchestration** — a LangGraph `reason → execute → respond` loop with a hard
  iteration cap; the agent writes Python and runs it as `execute_python_code`.
- **Hardened sandbox** — one ephemeral container per run: `--network none`, `--cap-drop ALL`,
  `no-new-privileges`, read-only rootfs, non-root, memory/CPU/PID/wall-clock limits. Swappable
  isolation: `docker` (default) · `gvisor` (runsc) · `e2b` (microVM stub). See [SECURITY.md](SECURITY.md).
- **God View** — a Next.js + React Flow canvas that animates each run live over a telemetry
  WebSocket, with token/cost and starter templates.
- **REST + MCP gateway** — `/v1/orchestrate`, `/v1/runs`; hashed API keys, per-key rate limits,
  admin key management; an **MCP** server at `/mcp` exposing the `orchestrate` tool.
- **Observability & evals** — OpenTelemetry **GenAI** spans (OTLP → Langfuse/Phoenix/Jaeger),
  per-run/per-key **token + cost metering** with **spend caps**, and an **eval harness** with a CI
  gate. See [OBSERVABILITY.md](OBSERVABILITY.md).
- **Template packs** — ready-to-run **legal**, **finance**, and **general** task templates at
  `GET /v1/templates`, surfaced as starters in the God View. See [docs/templates.md](docs/templates.md).

## Quickstart

### Option A — one command (Docker, full stack)

```bash
cp backend/.env.example backend/.env   # add your ANTHROPIC_API_KEY (skip if you already have it)
docker compose up --build              # backend :8000 · God View :3000
```

This builds the sandbox image, starts the backend (with the Docker CLI + host socket so it can
spawn sandbox containers, reading `backend/.env`), and serves the God View. **The socket mount is dev-only** — read the
security note at the top of [docker-compose.yml](docker-compose.yml) before using it anywhere shared.

### Option B — local dev (backend on host)

```bash
# 1. Sandbox image (the only place untrusted code runs)
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .

# 2. Backend
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -U -r backend/requirements.txt
cp backend/.env.example backend/.env   # add ANTHROPIC_API_KEY
cd backend && uvicorn app.main:app --reload

# 3. Frontend (separate shell)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

See [docs/quickstart.md](docs/quickstart.md) for the full walkthrough.

## Try it

```bash
curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"query": "Extract the parties, term, governing law, and termination notice from this contract and return JSON.", "context": "SERVICES AGREEMENT ... governed by the laws of the State of Delaware ..."}'

# Browse ready-made tasks:
curl http://localhost:8000/v1/templates
```

OpenAPI/Swagger is at `/docs`. Full endpoint reference: [docs/api-reference.md](docs/api-reference.md).

## Tests & quality gates

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q          # 41 tests (sandbox/eval suites need Docker)
../.venv/Scripts/python.exe -m ruff check .       # lint
../.venv/Scripts/python.exe -m evals.run --offline  # eval CI gate (deterministic, no LLM cost)
cd ../frontend && npm run build                   # typecheck + build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs lint, tests, the offline eval
gate, a gVisor isolation job, and the frontend build.

## Documentation

| Doc | What |
|---|---|
| [docs/quickstart.md](docs/quickstart.md) | Get running in < 5 minutes |
| [docs/api-reference.md](docs/api-reference.md) | REST + MCP endpoints |
| [docs/templates.md](docs/templates.md) | Legal / finance / general template packs |
| [docs/observability.md](docs/observability.md) → [OBSERVABILITY.md](OBSERVABILITY.md) | Tracing, metering, evals |
| [docs/security.md](docs/security.md) → [SECURITY.md](SECURITY.md) | Threat model & isolation |
| [ROADMAP.md](ROADMAP.md) · [HANDOFF.md](HANDOFF.md) | Plan & current state |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

## License

Apache-2.0 — see [LICENSE](LICENSE).
