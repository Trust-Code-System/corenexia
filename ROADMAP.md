# Corenexia — Build Roadmap

The full plan for **Corenexia**, the Infinite Dynamic Orchestrator. Domain is strictly **legal**
(contract analysis, compliance) and **general finance** (equities, market analysis) — no crypto.

Status legend: `[x]` done & verified · `[~]` partial / seam in place · `[ ]` not started.

The blueprint's 6 steps map to milestones below. We execute **sequentially, verifying each
step** before moving on.

---

## Milestone 1 — Backend MVP  `[x] COMPLETE & VERIFIED`

Goal: a working, sandboxed orchestration backend. 6/6 tests pass; app boots with a passing
Docker preflight.

### Step 1 — Scaffolding `[x]`
- [x] Monorepo layout (`backend/`, `docker/`, `frontend/` placeholder)
- [x] `requirements.txt`, `pyproject.toml` (ruff/pytest config)
- [x] `.env.example`, `.gitignore`, `README.md`, `docker-compose.yml`

### Step 2 — Orchestration engine (FastAPI + LangGraph) `[x]`
- [x] `config.py` — pydantic-settings (provider selection, sandbox limits, iteration cap)
- [x] Pluggable `LLMProvider` ABC with normalized message/tool blocks
- [x] `AnthropicProvider` — `claude-opus-4-8`, adaptive thinking, manual tool round-trip
- [x] `GeminiProvider` — explicit stub (proves the abstraction is pluggable)
- [x] LangGraph state machine: `reason → execute → respond` with iteration cap
- [x] `execute_python_code` tool definition + handler
- [x] FastAPI `POST /v1/orchestrate` + `/health`; sync graph run off the event loop

### Step 3 — Docker sandbox (security boundary) `[x]`
- [x] `sandbox.Dockerfile` (python:3.11-slim + pdfplumber, python-docx, pandas, numpy)
- [x] `SandboxRunner` ABC + `SandboxResult`
- [x] `DockerRunner` — ephemeral, `--network none`, capped mem/cpu/pids, read-only rootfs,
      non-root, cap-drop ALL, no-new-privileges, wall-clock timeout kill
- [x] `E2BRunner` stub (future microVM seam)
- [x] Docker preflight on startup (clear build hint if image missing)

### Step 4 seam — Telemetry event bus `[x]`
- [x] In-process `EventBus` + `OrchestratorEvent` (`thinking`/`writing_code`/
      `executing_sandbox`/`done`); graph emits at each phase
- [x] WebSocket endpoint to broadcast events (delivered in Milestone 2)

### Verification `[x]`
- [x] `pytest` — 6/6 (4 sandbox integration + 2 graph unit)
- [x] Sandbox network isolation + timeout-kill proven
- [x] App boots; `/health` → `sandbox_ready: true`
- [ ] **Live `POST /v1/orchestrate`** end-to-end (needs real `ANTHROPIC_API_KEY`; spends money — user-gated)

---

## Milestone 2 — WebSocket Telemetry (Blueprint Step 4)  `[ ]`

Goal: stream the orchestrator's live state to clients in real time.

- [ ] `app/api/ws.py` — `GET /ws/telemetry` (and/or per-run `/ws/runs/{run_id}`)
- [ ] On connect: `bus.subscribe()` → async queue; forward each event as JSON; clean up on
      disconnect (`bus.unsubscribe()`)
- [ ] Make orchestration runs addressable by `run_id` so a client can watch one run
- [ ] Decide run model: fire-and-forget with WS follow, or `POST` returns `run_id` immediately
      and results arrive over WS
- [ ] Emit richer events (generated code preview, per-step stdout snippet, errors)
- [ ] Verify: connect a WS client, POST a query, observe the event sequence live

---

## Milestone 3 — Frontend "God View" (Blueprint Step 5)  `[x] COMPLETE & VERIFIED`

Goal: the uncluttered dark-themed admin canvas that visualizes the orchestrator.

- [x] Scaffold Next.js 14 (App Router) + TypeScript + Tailwind in `frontend/`
- [x] Theme: deep navy `bg-slate-900`, charcoal `bg-slate-800` sidebars, minimalist borders,
      crisp typography (sky accent)
- [x] React Flow (`@xyflow/react`) canvas component (`components/OrchestratorCanvas.tsx`)
- [x] WebSocket client hook subscribing to telemetry (`lib/useTelemetry.ts`)
- [x] Orchestrator phases as nodes: a sandbox node appears on `executing_sandbox` start with a
      glowing animated edge, turns green/red on complete, then vanishes
- [x] Query composer panel + live status badge + health indicator
- [x] Live event log with code + stdout previews; answer/result panel
- [x] Verify: `next build` passes (typecheck clean); dev server serves the God View (HTTP 200)
- [ ] Manual visual confirmation against a live backend run (user-gated — needs API key)

---

## Milestone 4 — Universal Export: API Keys + Gateway (Blueprint Step 6)  `[x] COMPLETE & VERIFIED`

Goal: external apps query the engine with their own key, inheriting the full reasoning engine.

- [x] API key model: generate, **hash-at-rest** (SHA-256), list, revoke, usage metering
      (SQLite via `app/gateway/keys.py`)
- [x] Bearer auth dependency on `/v1/*` (`app/gateway/auth.py`), opt-in via `AUTH_ENABLED`
- [x] Per-key sliding-window rate limiting (`app/gateway/ratelimit.py`)
- [x] OpenAPI/Swagger auto-published at `/docs` (FastAPI)
- [x] Admin key-management endpoints guarded by `ADMIN_TOKEN` (`app/api/admin.py`):
      `POST/GET/DELETE /admin/keys`
- [x] **MCP server surface** — `orchestrate` tool over streamable HTTP at `/mcp`
      (`app/mcp_server.py`, official `mcp` SDK), mounted in the FastAPI lifespan
- [x] Verify: 5 gateway tests (key lifecycle, 401/202/revoke, open-mode, 429 rate limit, MCP
      mount) + a **live MCP `tools/list` handshake** confirming `orchestrate` is exposed
- [ ] Frontend admin screen for keys (deferred to a polish pass)

---

## Milestone 5 — Production Hardening  `[~] CORE COMPLETE & VERIFIED`

Goal: make it safe and operable beyond local dev.

- [x] Structured logging + request tracing — `X-Request-ID` middleware correlates a request to
      its `run_id` telemetry (`app/observability.py`)
- [x] Persistence for runs (audit trail) — SQLite-backed `RunRegistry`, survives restart
      (`app/orchestrator/runs.py`)
- [x] LLM timeout + retry budget on the Anthropic client (`app/llm/anthropic_provider.py`)
- [x] Sandbox concurrency control — semaphore caps simultaneous containers
      (`SANDBOX_MAX_CONCURRENCY`)
- [x] Secrets hygiene — access middleware logs only method/path/status, never bodies/keys
- [x] CI: lint (ruff), tests, sandbox image build, frontend build (`.github/workflows/ci.yml`)
      — ruff passes clean locally; activates on push to GitHub
- [x] Backend Dockerfile (`docker/backend.Dockerfile`, referenced by compose)
- [x] Auth on the WebSocket (key via `?api_key=`/Bearer when `AUTH_ENABLED`) + CORS for the
      frontend (`ALLOWED_ORIGINS`)
- [ ] Cost controls: per-key token metering + spend caps (deferred — request metering exists;
      token/$ accounting is the next slice)
- [ ] Resource accounting dashboards; Redis-backed rate limiting for multi-process
- [ ] Run containerized backend with a chosen Docker-access model (files ready; runtime test
      deferred)

Verified: 18/18 backend tests pass (CORS + request-id, run persistence across instances, WS
auth accept/reject, key lifecycle, rate limit, MCP mount, sandbox isolation/timeout, graph),
`ruff check` clean.

---

## Strengthening Strategy (post-blueprint, research-backed)

Full strategy + market intelligence: `~/.claude/plans/project-nexus-the-cuddly-popcorn.md`.
Locked direction: **open-core**, **general engine + legal/finance flagship templates**,
**security-first**. Five bets: isolation moat · OTel observability+evals · code-mode/dynamic
synthesis · DX+templates+registry · open-core vertical flagship.

### Initiative A — Security & isolation moat  `[~] FIRST PASS COMPLETE & VERIFIED`
- [x] Swappable isolation backend `SANDBOX_RUNTIME=docker|gvisor|e2b` (`build_sandbox()`),
      hardened Docker default, `GvisorRunner` (`--runtime=runsc`), runtime-aware preflight
- [x] Docker defense-in-depth: seccomp knob (`SANDBOX_SECCOMP_PROFILE`, default filter kept),
      `--cap-drop ALL`, `no-new-privileges`, read-only rootfs, non-root, no-network default
- [x] `/mcp` closed with bearer auth when `AUTH_ENABLED` (stream-safe ASGI middleware)
- [x] `SECURITY.md` threat model + responsible disclosure + OAuth/gVisor roadmap
- [x] `tests/test_security.py` (8): host-secret non-inheritance, non-root, read-only rootfs,
      `/tmp` writable, egress blocked, memory cap enforced, MCP auth — **all run, not skipped**
- [x] CI: dedicated **gVisor job** runs the security+sandbox suite under `runsc` on Linux
- [ ] Full **MCP OAuth 2.1** (scoped tokens, `iss`/RFC 9207) — documented follow-up
- [ ] Egress allowlist proxy (pairs with Initiative D dynamic synthesis)

### Initiative B — Observability & evals  `[x] COMPLETE & VERIFIED`
- [x] OTel GenAI spans (agent/LLM-chat/tool) + OTLP/HTTP export, off by default (`app/telemetry/otel.py`)
- [x] Langfuse/Phoenix via standard OTLP env vars (`OBSERVABILITY.md`)
- [x] Eval harness `backend/evals/` — deterministic offline gate (fixtures + real sandbox) + `--live`, in CI
- [x] Token + cost metering per run/key; spend cap → 402 (closes the M5 cost-control item)
- Verified: 34 backend tests, ruff clean, frontend build green, offline eval gate 6/6.

### Initiative C — Adoption & DX  `[x] COMPLETE & VERIFIED (publish gated)`
- [x] One-command `docker compose up`: sandbox-image + backend (Docker CLI + host socket) +
  frontend (Next standalone). New `docker/frontend.Dockerfile`, reworked compose, root
  `.env.example` + `.dockerignore`. Config valid; all 3 images build & run.
- [x] Docs: README rewritten + `docs/` (quickstart, api-reference, templates, security, observability)
- [x] Flagship legal + finance + general template packs; `GET /v1/templates`; God-View starters
- [x] `LICENSE` (Apache-2.0) + `NOTICE` + `CONTRIBUTING.md`; MCP Registry + Smithery manifests
  staged as DRAFTS in `packaging/registry/` (NOT published)
- [ ] Gated/outward-facing: publish to registries; demo GIF; full compose `up` end-to-end (live key)
- Verified: 41 backend tests, ruff clean, frontend build green, eval gate 6/6.

### Initiatives D–E (next)
- **D — Differentiator:** code-mode/progressive tool disclosure, reusable skills, dynamic synthesis, MCP aggregation
- **E — Cloud/enterprise (open-core monetization):** managed sandboxes, RBAC/SSO, audit, billing

---

## Stretch / Future (deliberately deferred)  `[ ]`

- [ ] **Dynamic GitHub script ingestion** — let the orchestrator pull specialized open-source
      scripts to bridge missing skills. Kept behind the sandbox boundary; high security surface,
      so only after the core loop is proven and hardened.
- [ ] **E2B (Firecracker microVM) backend** — implement `E2BRunner` for ~150ms true-microVM
      isolation; switch via config with no graph changes.
- [ ] Multi-tool surface beyond `execute_python_code` (e.g. retrieval, document upload)
- [ ] Multi-LLM routing (cost/latency-aware provider selection)
- [ ] Streaming LLM responses (the SDK helper) for long outputs
- [ ] Input-file mounting path hardening for cross-platform (Windows Docker Desktop)

---

## How to verify the current build

```bash
# Sandbox image (untrusted-code base) — requires Docker running
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .

# Backend deps
python -m venv .venv && .venv\Scripts\activate   # (or: source .venv/bin/activate)
pip install -U -r backend/requirements.txt

# Tests (test_sandbox needs Docker; test_graph does not)
pytest backend/tests

# Run + try it
cp backend/.env.example backend/.env   # add ANTHROPIC_API_KEY
cd backend && uvicorn app.main:app --reload
# POST the sample legal query from README.md to http://localhost:8000/v1/orchestrate
```

## Decision log
- **Sandbox:** Docker local now, abstracted for E2B later.
- **LLM:** Pluggable; default Claude `claude-opus-4-8`; Gemini stubbed.
- **Scope:** Backend-first, verified before any UI.
- **Deferred for safety:** dynamic GitHub ingestion until the core loop is hardened.
