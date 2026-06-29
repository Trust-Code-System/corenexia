"""MCP OAuth 2.1 tests (Initiative A follow-up). No Docker, no network, no live LLM.

Covers token issuance (client_credentials), discovery metadata, validation (iss/aud/exp/scope),
and that a scoped token is accepted in place of a static API key on /v1 and /mcp.
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import admin_router
from app.api.oauth import oauth_router
from app.api.routes import router
from app.config import settings
from app.gateway import oauth
from app.gateway.keys import KeyStore
from app.gateway.ratelimit import RateLimiter
from app.orchestrator.graph import build_orchestrator
from app.telemetry.events import EventBus
from tests.test_gateway import ADMIN_TOKEN
from tests.test_graph import FakeSandbox, ScriptedProvider


def make_app(tmp_path) -> FastAPI:
    provider = ScriptedProvider()
    sandbox = FakeSandbox(stdout='{"ok": true}')
    app = FastAPI()
    app.state.bus = EventBus()
    app.state.runs = None
    app.state.auth_enabled = True
    app.state.admin_token = ADMIN_TOKEN
    app.state.keys = KeyStore(str(tmp_path / "keys.db"))
    app.state.rate_limiter = RateLimiter(0)
    app.state.provider = provider
    app.state.sandbox = sandbox
    app.state.sandbox_ready = True
    app.state.sandbox_message = "fake"
    app.state.orchestrator = build_orchestrator(provider, sandbox, app.state.bus)
    app.include_router(router)
    app.include_router(oauth_router)
    app.include_router(admin_router)
    return app


def _mint_key(client: TestClient) -> str:
    created = client.post(
        "/admin/keys", json={"name": "oauth"}, headers={"X-Admin-Token": ADMIN_TOKEN}
    )
    return created.json()["api_key"]


# --- discovery metadata --------------------------------------------------


def test_metadata_endpoints(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        asm = client.get("/.well-known/oauth-authorization-server").json()
        assert asm["token_endpoint"].endswith("/oauth/token")
        assert "client_credentials" in asm["grant_types_supported"]
        assert oauth.SCOPE_RUN in asm["scopes_supported"]

        prm = client.get("/.well-known/oauth-protected-resource").json()
        assert prm["resource"] == settings.oauth_audience
        assert settings.oauth_issuer in prm["authorization_servers"]


# --- token endpoint ------------------------------------------------------


def test_token_via_form_and_basic(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        api_key = _mint_key(client)

        # client_secret form field
        r = client.post("/oauth/token", data={"grant_type": "client_credentials",
                                              "client_secret": api_key})
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] > 0
        assert oauth.SCOPE_RUN in body["scope"]

        # HTTP Basic
        basic = base64.b64encode(f"client:{api_key}".encode()).decode()
        r2 = client.post("/oauth/token", data={"grant_type": "client_credentials"},
                         headers={"Authorization": f"Basic {basic}"})
        assert r2.status_code == 200


def test_token_errors(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        api_key = _mint_key(client)
        # bad grant
        bad = client.post("/oauth/token", data={"grant_type": "password", "client_secret": api_key})
        assert bad.status_code == 400
        assert bad.json()["error"] == "unsupported_grant_type"
        # missing creds
        none = client.post("/oauth/token", data={"grant_type": "client_credentials"})
        assert none.status_code == 401
        # invalid key
        invalid = client.post("/oauth/token", data={"grant_type": "client_credentials",
                                                    "client_secret": "cnx_not_real"})
        assert invalid.status_code == 401


def test_scoped_token_accepted_on_v1(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        api_key = _mint_key(client)
        token = client.post("/oauth/token", data={"grant_type": "client_credentials",
                                                  "client_secret": api_key}).json()["access_token"]

        # No credentials → 401
        assert client.post("/v1/orchestrate", json={"query": "x"}).status_code == 401
        # Scoped token works in place of the API key
        ok = client.post("/v1/orchestrate", json={"query": "x"},
                         headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200


# --- validation units ----------------------------------------------------


def test_validate_rejects_bad_issuer_audience_and_scope(monkeypatch):
    token, _, _ = oauth.issue_token("key-1", [oauth.SCOPE_READ])

    # valid token, but missing the required scope
    with pytest.raises(oauth.OAuthError) as ei:
        oauth.validate_token(token, required_scope=oauth.SCOPE_RUN)
    assert ei.value.code == "insufficient_scope"

    # issuer mismatch (RFC 9207)
    monkeypatch.setattr(settings, "oauth_issuer", "https://evil.example.com")
    with pytest.raises(oauth.OAuthError):
        oauth.validate_token(token)


def test_validate_rejects_expired(monkeypatch):
    monkeypatch.setattr(settings, "oauth_token_ttl_seconds", -10)  # already expired
    token, _, _ = oauth.issue_token("key-1", [oauth.SCOPE_RUN])
    with pytest.raises(oauth.OAuthError):
        oauth.validate_token(token)
