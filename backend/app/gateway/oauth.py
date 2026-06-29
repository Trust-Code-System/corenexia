"""MCP OAuth 2.1 — scoped, short-lived access tokens (Initiative A follow-up).

The MCP server acts as an OAuth 2.1 **Resource Server**. Clients exchange a Corenexia API key
(the OAuth *client secret*) for a short-lived, scoped **JWT** at `/oauth/token` via the
`client_credentials` grant, then present it as `Authorization: Bearer <jwt>`. Static API keys keep
working alongside tokens for backward compatibility.

Validation enforces, per OAuth 2.1 / RFC 9207:
  * a valid HS256 signature,
  * `iss` == our issuer (RFC 9207 issuer validation),
  * `aud` == our audience (the token was minted for this resource),
  * `exp` not passed (short-lived),
  * the required scope is present.

We publish Authorization Server Metadata (RFC 8414) and Protected Resource Metadata (RFC 9728) so
spec-compliant MCP clients can discover the endpoints.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import jwt

from app.config import settings

ALGORITHM = "HS256"

# Scopes Corenexia understands.
SCOPE_RUN = "orchestrate:run"     # start orchestrations / call the MCP tool
SCOPE_READ = "orchestrate:read"   # read run status/results
SUPPORTED_SCOPES = [SCOPE_RUN, SCOPE_READ]
DEFAULT_SCOPES = [SCOPE_RUN, SCOPE_READ]

# Per-process fallback secret if none configured (tokens won't survive a restart — fine for dev).
_EPHEMERAL_KEY = secrets.token_urlsafe(48)


class OAuthError(Exception):
    """Raised when a token is missing/invalid/expired or lacks a required scope."""

    def __init__(self, message: str, *, code: str = "invalid_token"):
        super().__init__(message)
        self.code = code


@dataclass
class TokenClaims:
    subject: str           # the API key id the token was issued to
    scopes: list[str]
    issuer: str
    audience: str
    expires_at: int

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def _signing_key() -> str:
    return settings.oauth_signing_key or settings.admin_token or _EPHEMERAL_KEY


def normalize_scopes(requested: str | None) -> list[str]:
    """Parse a space-delimited scope string, keeping only supported scopes. Empty → defaults."""
    if not requested:
        return list(DEFAULT_SCOPES)
    asked = [s for s in requested.split() if s]
    granted = [s for s in asked if s in SUPPORTED_SCOPES]
    return granted or list(DEFAULT_SCOPES)


def issue_token(subject: str, scopes: list[str]) -> tuple[str, int, list[str]]:
    """Mint a signed access token for `subject`. Returns (jwt, expires_in_seconds, scopes)."""
    now = int(time.time())
    ttl = settings.oauth_token_ttl_seconds
    payload = {
        "iss": settings.oauth_issuer,
        "aud": settings.oauth_audience,
        "sub": subject,
        "scope": " ".join(scopes),
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
        "jti": secrets.token_urlsafe(12),
    }
    token = jwt.encode(payload, _signing_key(), algorithm=ALGORITHM)
    return token, ttl, scopes


def validate_token(token: str, required_scope: str | None = None) -> TokenClaims:
    """Decode + verify a token. Raises OAuthError on any failure or missing scope."""
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=[ALGORITHM],
            audience=settings.oauth_audience,
            issuer=settings.oauth_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise OAuthError("Token expired.", code="invalid_token") from exc
    except jwt.InvalidIssuerError as exc:
        raise OAuthError("Token issuer mismatch.", code="invalid_token") from exc
    except jwt.InvalidAudienceError as exc:
        raise OAuthError("Token audience mismatch.", code="invalid_token") from exc
    except jwt.PyJWTError as exc:
        raise OAuthError(f"Invalid token: {exc}", code="invalid_token") from exc

    scopes = [s for s in str(payload.get("scope", "")).split() if s]
    claims = TokenClaims(
        subject=str(payload["sub"]),
        scopes=scopes,
        issuer=str(payload["iss"]),
        audience=str(payload["aud"]),
        expires_at=int(payload["exp"]),
    )
    if required_scope and not claims.has_scope(required_scope):
        raise OAuthError(
            f"Token missing required scope '{required_scope}'.", code="insufficient_scope"
        )
    return claims


# --- discovery metadata --------------------------------------------------


def authorization_server_metadata() -> dict:
    """RFC 8414 Authorization Server Metadata."""
    iss = settings.oauth_issuer
    return {
        "issuer": iss,
        "token_endpoint": f"{iss}/oauth/token",
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "grant_types_supported": ["client_credentials"],
        "scopes_supported": SUPPORTED_SCOPES,
        "response_types_supported": ["token"],
    }


def protected_resource_metadata() -> dict:
    """RFC 9728 Protected Resource Metadata — points MCP clients at the authorization server."""
    iss = settings.oauth_issuer
    return {
        "resource": settings.oauth_audience,
        "authorization_servers": [iss],
        "scopes_supported": SUPPORTED_SCOPES,
        "bearer_methods_supported": ["header"],
    }
