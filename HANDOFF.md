# Corenexia — Project State & Handoff

**What it is:** an open, self-hostable **Infinite Dynamic Orchestrator** — an API/MCP gateway
where an AI agent, when it lacks a tool, **writes Python on the fly and runs it in a hardened,
ephemeral sandbox**, then returns structured results. Visual "God View" frontend. Domain flagship:
legal (contract analysis, compliance) + general finance.

**Strategy locked:** open-core · general-purpose engine with legal/finance flagship templates ·
security-first. Full strategy + market research: `~/.claude/plans/project-nexus-the-cuddly-popcorn.md`.

**Status:** Blueprint (M1–M5) complete + Strategy Initiative A (security moat) first pass complete.
Everything **struck through** below is done and verified.

---

## Environment / how to run (Windows 11, this machine)

- Python venv: `.venv` (Python 3.11). Backend deps installed.
- `ANTHROPIC_API_KEY` is set in `backend/.env` (git-ignored). Live LLM calls cost money.
- Docker Desktop must be running; sandbox image: `docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .`
- Backend: `cd backend && ../.venv/Scripts/uvicorn app.main:app --reload`  (or `python -m uvicorn ...`)
- Frontend: `cd frontend && npm run dev`  (Next 16 + React 19, 0 vulns)
- Tests: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`  → **34 passing**
- Lint: `./.venv/Scripts/python.exe -m ruff check backend` → clean
- Eval gate: `cd backend && ../.venv/Scripts/python.exe -m evals.run --offline` → 6/6, GATE PASSED
- Observability: see `OBSERVABILITY.md` (OTel tracing, token/cost metering, evals)

---

## Roadmap (done = struck through)

### Milestone 1 — Backend MVP ✅
- ~~Monorepo scaffold; FastAPI + LangGraph orchestrator (`reason → execute → respond`, iteration cap)~~
- ~~Pluggable `LLMProvider` (Anthropic `claude-opus-4-8` default, adaptive thinking; Gemini stub)~~
- ~~`execute_python_code` tool + hardened Docker sandbox (`SandboxRunner` interface, E2B stub)~~
- ~~`POST /v1/orchestrate`, `/health`; telemetry event bus; 6 tests~~

### Milestone 2 — WebSocket Telemetry ✅
- ~~Thread-safe `EventBus` (worker-thread → loop via `call_soon_threadsafe`)~~
- ~~`GET /ws/telemetry` (global God View + `?run_id=` filter, auto-close on terminal)~~
- ~~Background runs: `POST /v1/runs`, `GET /v1/runs/{id}`; enriched events (code/stdout previews)~~

### Milestone 3 — Frontend "God View" ✅
- ~~Next.js (App Router) + Tailwind, deep-navy/charcoal theme~~
- ~~React Flow canvas: sandbox nodes appear/pulse/vanish from live telemetry~~
- ~~Query composer, status badge, health indicator, live event log, answer panel~~
- ~~Migrated to **Next 16 + React 19**, `npm audit` = 0 vulnerabilities, build green~~

### Milestone 4 — API Keys + REST/MCP Gateway ✅
- ~~API key store (SQLite, SHA-256 hashed, usage metering); Bearer auth on `/v1/*` (`AUTH_ENABLED`)~~
- ~~Per-key rate limiting; admin key management `POST/GET/DELETE /admin/keys` (`ADMIN_TOKEN`)~~
- ~~**MCP server** (`orchestrate` tool) over streamable HTTP at `/mcp` — verified via live `tools/list`~~

### Milestone 5 — Production Hardening (core) ✅
- ~~Request tracing (`X-Request-ID` middleware) + structured logging~~
- ~~CORS for the frontend (`ALLOWED_ORIGINS`)~~
- ~~Run persistence (SQLite-backed `RunRegistry`, survives restart — audit trail)~~
- ~~Sandbox concurrency semaphore (`SANDBOX_MAX_CONCURRENCY`)~~
- ~~LLM client timeout + retry budget~~
- ~~WebSocket auth when `AUTH_ENABLED`~~
- ~~CI workflow (`.github/workflows/ci.yml`) + backend Dockerfile~~
- ~~Cost controls: per-key **token/$ metering + spend caps** (402 block) — done in Initiative B~~
- [ ] Redis-backed rate limiting (multi-process); containerized-backend runtime test

### Strategy Initiative A — Security & Isolation Moat ✅ (first pass)
- ~~Swappable isolation: `SANDBOX_RUNTIME=docker|gvisor|e2b`; `GvisorRunner` (`--runtime=runsc`); runtime-aware preflight~~
- ~~Docker defense-in-depth: seccomp knob (`SANDBOX_SECCOMP_PROFILE`), cap-drop ALL, no-new-privileges, read-only rootfs, non-root, no-network default~~
- ~~`/mcp` closed with bearer auth when `AUTH_ENABLED` (stream-safe ASGI middleware)~~
- ~~`SECURITY.md` threat model + responsible disclosure~~
- ~~`tests/test_security.py` (8): host-secret non-inheritance, non-root, read-only rootfs, `/tmp` writable, egress blocked, memory cap, MCP auth — all run~~
- ~~CI gVisor job (runs security+sandbox suite under `runsc` on Linux)~~
- ~~**MCP OAuth 2.1** — scoped/short-lived JWTs via `/oauth/token` (`client_credentials`),
  validated for sig/`iss`(RFC 9207)/`aud`/`exp`/scope; RFC 8414/9728 metadata; `/mcp` needs
  `orchestrate:run`; static keys still work (`app/gateway/oauth.py`, `app/api/oauth.py`)~~
- ~~**Egress allowlist proxy** — opt-in (`SANDBOX_EGRESS_*`); default stays `--network none`;
  filtering CONNECT proxy permits only allowlisted hosts (`app/sandbox/egress.py`)~~
- Follow-ups: per-`/v1`-route scope enforcement; RS256/JWKS + dynamic client registration

### Initiative B — Observability & Evals  ✅ COMPLETE & VERIFIED
- ~~Emit **OpenTelemetry GenAI** spans (agent/LLM-chat/tool) from `app/telemetry/otel.py`,
  instrumented in `orchestrator/graph.py`; OTLP/HTTP exporter, off by default (`OTEL_ENABLED`)~~
- ~~**Langfuse/Phoenix** integration via standard OTLP env vars — documented in `OBSERVABILITY.md`~~
- ~~**Eval harness** `backend/evals/` (dataset.json legal+finance, evaluators, runner): deterministic
  offline gate (`--offline`, fixtures + real sandbox, no LLM cost) + `--live`; wired into CI~~
- ~~**Token + cost metering** (`app/telemetry/metering.py`): per-run usage in API/telemetry/persisted;
  per-key token+cost counters; **spend cap → 402** (`PUT /admin/keys/{id}/spend-cap`)~~
- Verified: **34 backend tests** (incl. test_metering, test_otel, test_evals), ruff clean,
  frontend build green (God View shows tokens + $ cost), offline eval gate 6/6.
- Follow-ups: per-token cache-cost pricing; Gemini usage mapping (provider still stubbed).

### Initiative C — Adoption & DX  ✅ COMPLETE & VERIFIED (publish step gated)
- ~~One-command `docker compose up` full stack: sandbox-image + backend (Docker CLI + socket) +
  frontend (Next standalone). `docker/frontend.Dockerfile`, reworked `docker-compose.yml` +
  root `.env.example` + `.dockerignore`. Compose config valid; **all three images build & run**
  (frontend serves 200, backend image has docker CLI 27.5.1)~~
- ~~Docs: README rewritten to current state + `docs/` set (quickstart, api-reference, templates,
  security, observability) cross-linked to canonical `SECURITY.md` / `OBSERVABILITY.md`~~
- ~~Flagship **legal** + **finance** + **general** template packs (`backend/app/templates/packs/`),
  read-only `GET /v1/templates[/packs|/{id}]`, surfaced as God-View starter dropdown (7 tests)~~
- ~~`LICENSE` (Apache-2.0) + `NOTICE` + `CONTRIBUTING.md`; **MCP Registry + Smithery manifests
  staged as DRAFTS** in `packaging/registry/` (placeholders, NOT published)~~
- **Still gated / TODO:** actually publishing to MCP Registry + Smithery (outward-facing — needs
  your go-ahead + real GitHub owner/URL); a demo GIF (needs a screen recording); full
  `docker compose up` end-to-end runtime test (socket-mounted backend spawning sandboxes; needs a
  live API key — costs money).
- Verified: **41 backend tests** (+7 templates), ruff clean, frontend build green, eval gate 6/6.

### Initiative D — Differentiator Features  ✅ COMPLETE & VERIFIED
- ~~**Reusable skills + progressive tool disclosure** (1–2): `save_skill`/`load_skill`, catalog in
  prompt; `SkillStore` + `/v1/skills`. 5 tests~~
- ~~**Dynamic integration synthesis + human-approval gate** (3): `request_egress` → admin approval
  adds host to the live `EgressPolicy` the proxy enforces (`/admin/egress/*`). 5 tests~~
- ~~**Gemini provider** (4a): real `google-genai` implementation, translation unit-tested; live gated~~
- ~~**True MCP aggregation** (4b): `McpAggregator` connects upstream MCP servers, namespaces +
  re-exposes their tools (`<up>__<tool>`), proxies calls; `/v1/mcp/upstreams`
  (`app/orchestrator/mcp_aggregator.py`). 7 tests~~
- ~~**Multi-LLM routing** (4c): `RoutingProvider` cost-aware ordering + error failover
  (`app/llm/router.py`, `LLM_ROUTING_*`). 6 tests~~
- ~~**Streaming** (4c): SSE `POST /v1/orchestrate/stream` (run-level, reuses the event bus). 1 test~~
- Remaining stretch: **token-level** LLM streaming (needs the sync graph reworked — separate effort).
- Verified: **83 backend tests**, ruff clean, frontend build green.

### Initiative E — Cloud & Enterprise (open-core monetization)  ⬜ LATER
- [ ] Managed cloud (hosted sandboxes), org/RBAC, SSO, audit logs, SOC 2 path, usage/seat billing, EU-AI-Act/Colorado-AI-Act readiness

---

## Always user-gated (do NOT do without explicit approval)
- Live LLM orchestration runs (spends money) — key is present in `backend/.env`.
- Anything outward-facing: publishing to registries, deploying cloud, billing, sending messages.

## Key files map
- Orchestrator: `backend/app/orchestrator/{graph,state,tools,runs}.py`
- Sandbox: `backend/app/sandbox/{base,docker_runner,gvisor_runner,e2b_runner}.py`
- LLM: `backend/app/llm/{base,anthropic_provider,gemini_provider}.py`
- Gateway: `backend/app/gateway/{keys,auth,ratelimit}.py`
- API: `backend/app/api/{routes,admin,templates,ws}.py`; MCP: `backend/app/mcp_server.py`
- Telemetry/metering/tracing: `backend/app/telemetry/{events,metering,otel}.py`
- Templates: `backend/app/templates/{registry.py,packs/*.json}`
- Evals: `backend/evals/{run,evaluators,fixtures,dataset.json}`
- App wiring: `backend/app/main.py`, `backend/app/config.py`, `backend/app/observability.py`
- Frontend: `frontend/app/`, `frontend/components/`, `frontend/lib/`
- Deploy: `docker-compose.yml`, `docker/{backend,frontend,sandbox}.Dockerfile`, `.env.example`
- Docs: `README.md`, `docs/`, `OBSERVABILITY.md`, `SECURITY.md`, `ROADMAP.md`, `CONTRIBUTING.md`,
  `LICENSE`; registry drafts in `packaging/registry/`; strategy plan at
  `~/.claude/plans/project-nexus-the-cuddly-popcorn.md`

---

## ▶️ Continuation prompt (paste into a new session)

```
You are continuing work on Corenexia (c:\Users\Admin\Desktop\corenexia), an open-core
"Infinite Dynamic Orchestrator": an AI agent that writes Python and runs it in a hardened
sandbox, with a React Flow "God View" and a REST + MCP gateway.

First, read these to load full context:
- HANDOFF.md (project state; done items are struck through)
- ROADMAP.md and SECURITY.md
- the strategy plan at ~/.claude/plans/project-nexus-the-cuddly-popcorn.md

Status: Milestones 1–5 complete; Initiatives A (security moat + OAuth 2.1 + egress proxy),
B (observability & evals), C (adoption & DX), and D (differentiator) ALL complete. 83 backend
tests pass; ruff clean; frontend builds; offline eval gate 6/6; all 3 Docker images build. The
code is PUBLIC at github.com/Trust-Code-System/corenexia (pushed). MCP Registry + Smithery
listings are staged but NOT submitted — they need interactive auth (see packaging/registry/RUNBOOK.md).

Open work (pick per the user):
  - Initiative E — Cloud & enterprise (managed sandboxes, org/RBAC, SSO, audit, billing, SOC 2).
  - Token-level LLM streaming (stretch; needs the sync graph reworked).
  - Gated/outward-facing: submit MCP Registry + Smithery listings (RUNBOOK.md; gh authed as
    Lingz450; needs `write:packages` refresh + `mcp-publisher login`), demo GIF, full
    `docker compose up` end-to-end (live API call), one real orchestration in the God View.

Rules: keep the existing 83 tests + frontend build green; run ruff. Do NOT make live LLM
calls or any outward-facing/paid action (incl. publishing to registries) without my explicit
approval (my ANTHROPIC_API_KEY is in backend/.env). Windows local uses hardened Docker;
gVisor/microVM are Linux/CI/cloud. Verify each change with pytest before reporting.

Start by confirming the plan, then proceed.
```
