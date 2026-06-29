# Security

Corenexia executes **AI-generated, untrusted code**. Isolating that execution is the product's
single most important property. The full threat model, controls, and responsible-disclosure policy
live in **[../SECURITY.md](../SECURITY.md)** — start there. This page is a summary.

## Isolation at a glance

Every run gets **one ephemeral container** that is dropped at the end (`--rm`), with:

- `--network none` — no egress by default (no exfiltration / SSRF)
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only rootfs, non-root (`--user 65534`)
- Docker's default seccomp filter (configurable via `SANDBOX_SECCOMP_PROFILE`)
- `--memory` / `--cpus` / `--pids-limit` / wall-clock timeout, plus a concurrency semaphore
- **No host env** is passed in — the sandbox can't read your API keys (asserted by a test)

## Swappable isolation backends

Set `SANDBOX_RUNTIME`:

- `docker` — hardened container. Default; works on Windows/macOS/Linux. What the test suite verifies.
- `gvisor` — runs under gVisor (`runsc`) for user-space syscall interception. **Linux deploy/CI/cloud.**
- `e2b` — Firecracker microVMs (stubbed for the cloud tier).

> Containers alone proved insufficient for untrusted code in 2026 incident research, so stronger
> isolation is a first-class, swappable option — not an afterthought.

## Docker access in the compose stack

The one-command stack mounts the host Docker socket into the backend so it can spawn sandbox
containers. **This is dev-only** and grants the backend full control of the host daemon. For shared
or production deployments, use a remote/rootless daemon (`DOCKER_HOST`) or run the backend on the
host. See the security note in [../docker-compose.yml](../docker-compose.yml).

## Gateway

- Hashed (SHA-256-at-rest) Bearer API keys on `/v1/*` and `/mcp` when `AUTH_ENABLED=true`
- Per-key rate limiting and **token/cost spend caps** (402 when exceeded)
- Admin key management behind `ADMIN_TOKEN`

## Verifying the boundary

```bash
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .
pytest backend/tests/test_security.py -v
```

The suite proves host secrets aren't visible, the process is non-root, the rootfs is read-only,
network egress is blocked, and the memory cap is enforced.

## Roadmap

MCP OAuth 2.1 (scoped/short-lived tokens, `iss` validation), an egress allowlist proxy before any
outbound is enabled, and tool/supply-chain integrity checks. Details in [../SECURITY.md](../SECURITY.md).

Report vulnerabilities privately per [../SECURITY.md](../SECURITY.md) — please don't open public
issues for undisclosed issues.
