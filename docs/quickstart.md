# Quickstart

Get Corenexia running and watch it write + run code in under five minutes.

## Prerequisites

- **Docker** (Desktop on Windows/macOS, Engine on Linux) — the sandbox runs untrusted code in
  ephemeral containers.
- An **`ANTHROPIC_API_KEY`** (default LLM provider is Claude). Live orchestration spends money.
- For local dev: **Python 3.11** and **Node 22**.

## Option A — one command (Docker, full stack)

```bash
cp backend/.env.example backend/.env   # add ANTHROPIC_API_KEY (skip if you already have it)
docker compose up --build
```

- God View: <http://localhost:3000>
- API + Swagger: <http://localhost:8000/docs>

`docker compose` builds the sandbox image, starts the backend (with the Docker CLI and the host
socket mounted so it can spawn sandbox containers), and serves the God View.

> ⚠ **The mounted Docker socket is for local dev only.** It gives the backend full control of the
> host Docker daemon. For anything shared/production, point the backend at a remote or rootless
> daemon instead (`DOCKER_HOST`), or run the backend on the host. See [../SECURITY.md](../SECURITY.md).

## Option B — local dev (backend on the host)

```bash
# 1. Build the sandbox image (the only place untrusted code runs)
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .

# 2. Backend
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -U -r backend/requirements.txt
cp backend/.env.example backend/.env     # add ANTHROPIC_API_KEY
cd backend && uvicorn app.main:app --reload

# 3. Frontend (separate shell)
cd frontend
npm install
npm run dev      # http://localhost:3000  (NEXT_PUBLIC_API_BASE defaults to http://localhost:8000)
```

## First run

From the God View, pick a **starter template** (legal / finance / general) or type a task, then
**Run orchestrator**. Watch the node move through `thinking → writing_code → executing_sandbox`,
a sandbox node appear with a pulsing edge and vanish on completion, and the streamed events,
token/cost, and final answer on the right.

Or from the CLI:

```bash
curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"query": "A stock trades at $150 with EPS $5. Compute the P/E. Print JSON and answer."}'
```

## Enabling auth (optional)

```bash
# in .env (compose) or backend/.env (local)
AUTH_ENABLED=true
ADMIN_TOKEN=<a long random value>
```

```bash
# Mint a key (shown once), then call with it
curl -X POST http://localhost:8000/admin/keys \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"name":"my-app"}'

curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Authorization: Bearer cnx_..." -H "Content-Type: application/json" -d '{"query":"..."}'
```

## Next

- [api-reference.md](api-reference.md) — every endpoint
- [templates.md](templates.md) — the legal/finance/general packs
- [observability.md](observability.md) — tracing, metering, evals
- [security.md](security.md) — isolation & threat model
