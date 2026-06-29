# Security Policy

Corenexia executes **AI-generated, untrusted code**. Isolating that execution is the product's
single most important security property. This document describes the threat model, the controls
in place, and the roadmap.

## Reporting a vulnerability

Please report suspected vulnerabilities privately to **security@corenexia.dev** (or open a GitHub
security advisory). Do not file public issues for undisclosed vulnerabilities. We aim to
acknowledge within 72 hours and to coordinate disclosure.

## Threat model

| Threat | Mitigation |
|---|---|
| **Untrusted code escapes the sandbox to the host** | One ephemeral container per run, dropped at the end (`--rm`). Non-root (`--user 65534`), all capabilities dropped (`--cap-drop ALL`), `no-new-privileges`, read-only rootfs, Docker's default seccomp filter. Optional **gVisor (`runsc`)** runtime for syscall-level isolation in Linux deploy/CI. |
| **Data exfiltration / SSRF from generated code** | No network by default (`--network none`). When outbound is explicitly enabled (`SANDBOX_EGRESS_ENABLED`), traffic is forced through an **allowlist egress proxy** (`app/sandbox/egress.py`) that permits only configured hosts and refuses everything else — never raw networking. |
| **Host secrets / API keys leak into the sandbox** | The container inherits **no** host environment; the runner passes no `--env`. Asserted by `tests/test_security.py::test_host_secrets_not_visible_in_sandbox`. |
| **Resource exhaustion (CPU/memory/PID/wall-clock)** | `--memory` + `--memory-swap` (OOM-killed), `--cpus`, `--pids-limit`, per-run wall-clock timeout that force-kills the container, and a concurrency semaphore capping simultaneous containers. |
| **Runaway agent loops** | Hard iteration cap in the orchestrator graph. |
| **Unauthorized API / MCP access** | Bearer API keys (hashed at rest) on `/v1/*` and `/mcp` when `AUTH_ENABLED`; per-key rate limiting; admin key management behind `ADMIN_TOKEN`. Plus **OAuth 2.1 scoped, short-lived tokens** (`/oauth/token`, `client_credentials`) validated for signature, `iss` (RFC 9207), `aud`, `exp`, and scope; `/mcp` requires the `orchestrate:run` scope. |
| **Tool poisoning / prompt injection (MCP)** | The orchestrator exposes a single first-party tool today (`execute_python_code`) — no untrusted upstream tool metadata enters the system prompt. See roadmap for aggregation guardrails. |

## Isolation posture by platform

- **Local dev (Windows/macOS Docker Desktop):** hardened Docker (`SANDBOX_RUNTIME=docker`). This
  is the default and what the test suite verifies.
- **Linux deploy / CI / cloud:** set `SANDBOX_RUNTIME=gvisor` to run under gVisor (`runsc`) for
  user-space syscall interception — the defense recommended for running untrusted code. The
  runner's preflight verifies the runtime is registered with Docker and fails clearly if not.
- **Managed microVM:** `SANDBOX_RUNTIME=e2b` (Firecracker microVMs) is stubbed for the cloud tier.

> Why this matters: 2026 incident research found that **containers alone are insufficient** for
> untrusted code (documented sandbox escapes), so stronger isolation is a first-class, swappable
> option rather than an afterthought.

## Verifying the boundary

```bash
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .
pytest backend/tests/test_security.py -v
```

The suite proves: host secrets are not visible, the process is non-root, the rootfs is read-only
(`/tmp` is the only writable area), network egress is blocked, and the memory cap is enforced.

## Roadmap (hardening follow-ups)

- **MCP OAuth 2.1** ✅ *implemented*: scoped, short-lived JWTs via `/oauth/token`
  (`client_credentials`), validated for signature, `iss` (RFC 9207), `aud`, `exp`, and scope;
  `/mcp` requires `orchestrate:run`. Discovery via RFC 8414/9728 metadata. Static API keys still
  work for backward compatibility. *Follow-ups:* per-`/v1`-route scope enforcement; RS256/JWKS +
  dynamic client registration for third-party authorization servers.
- **Egress allowlist proxy** ✅ *implemented* (`app/sandbox/egress.py`): off by default
  (`--network none`); when `SANDBOX_EGRESS_ENABLED=true` the sandbox is routed through a filtering
  forward proxy that allows only `SANDBOX_EGRESS_ALLOWLIST` hosts (exact or `*.suffix`) and fails
  closed without a proxy URL. *Deployment note:* the egress network must be locked down so the
  proxy is the container's only route out (Linux/cloud); on Docker Desktop this confinement is a
  deployment concern. Pairs with Initiative D dynamic synthesis (+ human-approval gate).
- **Tool/supply-chain integrity**: pin + hash tool definitions; verify/scan any externally
  sourced code or MCP servers before they run; keep everything behind the sandbox boundary.
- **gVisor in CI**: run the sandbox suite under `runsc` on the Linux CI job in addition to Docker.
