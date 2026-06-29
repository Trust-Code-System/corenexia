"""OAuth 2.1 endpoints for MCP clients (Initiative A follow-up).

- `POST /oauth/token` — `client_credentials` grant: exchange a Corenexia API key (the client
  secret) for a short-lived, scoped JWT.
- `GET /.well-known/oauth-authorization-server` — RFC 8414 metadata.
- `GET /.well-known/oauth-protected-resource` — RFC 9728 metadata.

Discovery endpoints are public. The token endpoint authenticates the client with its API key via
either HTTP Basic (`client_secret`) or a `client_secret` form field.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from app.gateway import oauth

oauth_router = APIRouter(tags=["oauth"])


def _client_secret_from_basic(request: Request) -> str | None:
    """Extract the client secret from an HTTP Basic Authorization header, if present."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[len("Basic ") :].strip()).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    # client_id:client_secret — the secret is the Corenexia API key.
    _, _, secret = decoded.partition(":")
    return secret or None


@oauth_router.post("/oauth/token")
async def token(
    request: Request,
    grant_type: str = Form(...),
    scope: str | None = Form(None),
    client_secret: str | None = Form(None),
) -> JSONResponse:
    """OAuth 2.1 client_credentials token endpoint. The API key is the client secret."""
    if grant_type != "client_credentials":
        return JSONResponse(
            {"error": "unsupported_grant_type",
             "error_description": "Only client_credentials is supported."},
            status_code=400,
        )

    secret = client_secret or _client_secret_from_basic(request)
    if not secret:
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Missing client credentials."},
            status_code=401,
            headers={"WWW-Authenticate": "Basic"},
        )

    record = request.app.state.keys.verify(secret)
    if record is None:
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Invalid or revoked API key."},
            status_code=401,
        )

    scopes = oauth.normalize_scopes(scope)
    access_token, expires_in, granted = oauth.issue_token(record.id, scopes)
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": " ".join(granted),
        }
    )


@oauth_router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata() -> dict:
    return oauth.authorization_server_metadata()


@oauth_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict:
    return oauth.protected_resource_metadata()
