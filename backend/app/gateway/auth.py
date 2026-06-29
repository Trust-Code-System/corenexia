"""FastAPI auth dependencies for the gateway.

- `require_api_key` guards /v1/*. When `app.state.auth_enabled` is False the gateway runs open
  (local dev); when True it requires `Authorization: Bearer <key>`, verifies it against the
  KeyStore (which also meters usage), and enforces the per-key rate limit.
- `require_admin` guards /admin/* with the configured ADMIN_TOKEN.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Request

from app.gateway.keys import ApiKeyRecord


async def require_api_key(request: Request) -> ApiKeyRecord | None:
    if not getattr(request.app.state, "auth_enabled", False):
        return None  # open mode

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_key = auth[len("Bearer ") :].strip()
    record = request.app.state.keys.verify(raw_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")

    if not request.app.state.rate_limiter.allow(record.id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")

    return record


async def require_admin(
    request: Request, x_admin_token: str | None = Header(default=None)
) -> None:
    expected = getattr(request.app.state, "admin_token", None)
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin API disabled: set ADMIN_TOKEN in the environment to enable it.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token (header X-Admin-Token).")


# Re-exported for route decorators.
ApiKeyDep = Depends(require_api_key)
AdminDep = Depends(require_admin)


class MCPAuthMiddleware:
    """Pure-ASGI guard for the mounted MCP app.

    When `app.state.auth_enabled` is True, requests under `/mcp` must carry a valid API key as
    `Authorization: Bearer <key>`. Implemented as pure ASGI (not BaseHTTPMiddleware) so it never
    buffers the MCP streamable-HTTP / SSE response — on success it passes the stream through
    untouched; only auth failures short-circuit with a 401.

    (This closes the open MCP endpoint today; full MCP OAuth 2.1 — scoped tokens, `iss`
    validation — is the documented follow-up in SECURITY.md.)
    """

    def __init__(self, app, path_prefix: str = "/mcp"):
        self.app = app
        self.path_prefix = path_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        starlette_app = scope.get("app")
        auth_enabled = bool(getattr(getattr(starlette_app, "state", None), "auth_enabled", False))
        if not auth_enabled:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        raw_key = (
            authorization[len("Bearer ") :].strip()
            if authorization.startswith("Bearer ")
            else ""
        )
        keys = getattr(getattr(starlette_app, "state", None), "keys", None)
        if raw_key and keys is not None and keys.verify(raw_key) is not None:
            await self.app(scope, receive, send)
            return

        from starlette.responses import JSONResponse

        response = JSONResponse(
            {"detail": "Missing or invalid API key for MCP endpoint."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
