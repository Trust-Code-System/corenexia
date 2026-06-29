# API reference

Base URL: `http://localhost:8000`. Interactive OpenAPI/Swagger lives at `/docs`.

When `AUTH_ENABLED=true`, `/v1/*` (except the public template catalog) and `/mcp` require
`Authorization: Bearer <api_key>`; `/admin/*` requires `X-Admin-Token`.

## Orchestration

### `POST /v1/orchestrate`
Run synchronously and return the full result. Blocks until done.

Request:
```json
{ "query": "string (required)", "context": "string | null", "max_iterations": 6 }
```

Response:
```json
{
  "run_id": "…",
  "status": "done | max_iterations",
  "answer": "…",
  "iterations": 2,
  "steps": [
    { "tool": "execute_python_code", "code": "…", "stdout": "…", "stderr": "",
      "exit_code": 0, "timed_out": false, "duration_ms": 412 }
  ],
  "usage": { "input_tokens": 8421, "output_tokens": 1290, "total_tokens": 9711,
             "cost_usd": 0.0741, "llm_calls": 3 }
}
```

Errors: `402` spend cap reached · `502` orchestration failed · `503` sandbox not ready.

### `POST /v1/runs`
Start a run in the background; returns `202` with a `run_id` and a telemetry WebSocket URL. Watch
it live, then fetch the result.

```json
{ "run_id": "…", "status": "running", "telemetry_ws": "/ws/telemetry?run_id=…" }
```

### `GET /v1/runs/{run_id}`
Fetch a background run's status and (once finished) its result. Never blocked by spend caps.

### `GET /ws/telemetry?run_id=…`  (WebSocket)
Streams `OrchestratorEvent`s: `thinking`, `writing_code`, `executing_sandbox`, `done`, `error`,
each with `data` (code/stdout previews, exit codes, usage on `done`). Omit `run_id` for the global
"God View" feed. Requires `?api_key=` / Bearer when auth is enabled.

## Templates (public catalog)

- `GET /v1/templates?domain=legal|finance|general` — list ready-to-run task templates.
- `GET /v1/templates/packs` — list the packs.
- `GET /v1/templates/{id}` — one template.

Turn a template into a run by POSTing its `query` (+ optional `example_context`) to
`/v1/orchestrate`. See [templates.md](templates.md).

## Admin (header `X-Admin-Token`)

- `POST /admin/keys` `{ "name": "…" }` → `201` with the plaintext `api_key` (**shown once**).
- `GET /admin/keys` → keys with usage (`request_count`, `input_tokens`, `output_tokens`,
  `cost_usd`, `spend_cap_usd`).
- `DELETE /admin/keys/{id}` → `204` revoke.
- `PUT /admin/keys/{id}/spend-cap` `{ "spend_cap_usd": 25.0 | null }` → set/clear the USD cap.
  Once a key's `cost_usd` reaches its cap, new orchestration requests get `402`.

## Skills (reusable toolbox)

The agent saves working scripts as named skills (via the `save_skill`/`load_skill` tools) and
reloads them later. Browse/curate them here:

- `GET /v1/skills?q=…` — list skill summaries (name/description/tags/use_count; no code). Public.
- `GET /v1/skills/{name}` — one skill, including its code. Public.
- `POST /v1/skills` `{name, description, code, tags}` → `201` create/update (API key when auth on).
- `DELETE /v1/skills/{name}` → `204` (API key when auth on).

## OAuth 2.1 (for MCP clients)

- `POST /oauth/token` — `client_credentials` grant: send `grant_type=client_credentials` plus the
  API key as `client_secret` (form field or HTTP Basic). Returns a short-lived scoped JWT
  (`access_token`, `expires_in`, `scope`). Scopes: `orchestrate:run`, `orchestrate:read`.
- `GET /.well-known/oauth-authorization-server` — RFC 8414 metadata.
- `GET /.well-known/oauth-protected-resource` — RFC 9728 metadata.

Present the JWT as `Authorization: Bearer <token>` anywhere an API key is accepted; tokens are
validated for signature, `iss`, `aud`, `exp`, and scope. Static API keys keep working.

## MCP

- `POST /mcp` — streamable-HTTP MCP server exposing the `orchestrate` tool. Point any MCP client
  (Claude Desktop, MCP Inspector) at `http://localhost:8000/mcp`. When `AUTH_ENABLED=true` it
  accepts a Bearer API key or a scoped token carrying `orchestrate:run`.

## Health

- `GET /health` → `{ status, sandbox_ready, sandbox, llm_provider }`. Every response carries an
  `X-Request-ID` correlating it to telemetry.
