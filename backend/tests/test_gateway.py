"""Gateway tests — API key store, Bearer auth, rate limiting, admin endpoints, MCP mount.

No Docker, no API key, no network (fakes for the orchestrator). The MCP-mount test boots the
real app with a dummy key just to confirm the /mcp surface is wired.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import admin_router
from app.api.routes import router
from app.gateway.keys import KeyStore
from app.gateway.ratelimit import RateLimiter
from app.orchestrator.graph import build_orchestrator
from app.orchestrator.runs import RunRegistry
from app.telemetry.events import EventBus
from tests.test_graph import FakeSandbox, ScriptedProvider

ADMIN_TOKEN = "test-admin-token"


def make_app(tmp_path, *, auth_enabled=True, rate_per_min=60) -> FastAPI:
    provider = ScriptedProvider()
    sandbox = FakeSandbox(stdout='{"governing_law": "Delaware"}')

    app = FastAPI()
    app.state.bus = EventBus()
    app.state.runs = RunRegistry(str(tmp_path / "runs.db"))
    app.state.auth_enabled = auth_enabled
    app.state.admin_token = ADMIN_TOKEN
    app.state.keys = KeyStore(str(tmp_path / "keys.db"))
    app.state.rate_limiter = RateLimiter(rate_per_min)
    app.state.provider = provider
    app.state.sandbox = sandbox
    app.state.sandbox_ready = True
    app.state.sandbox_message = "fake"
    app.state.orchestrator = build_orchestrator(provider, sandbox, app.state.bus)
    app.include_router(router)
    app.include_router(admin_router)
    return app


# --- KeyStore unit -------------------------------------------------------


def test_keystore_lifecycle(tmp_path):
    store = KeyStore(str(tmp_path / "k.db"))
    raw, rec = store.create("integration-key")
    assert raw.startswith("cnx_")
    assert rec.request_count == 0

    verified = store.verify(raw)
    assert verified is not None
    assert verified.id == rec.id
    assert verified.request_count == 1  # metered

    assert store.verify("cnx_not-a-real-key") is None

    assert store.revoke(rec.id) is True
    assert store.verify(raw) is None  # revoked keys no longer validate
    assert store.revoke(rec.id) is False  # already revoked


# --- Auth + admin integration -------------------------------------------


def test_v1_requires_key_when_auth_enabled(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        # No key -> 401
        assert client.post("/v1/runs", json={"query": "x"}).status_code == 401

        # Admin without token -> 401
        assert client.post("/admin/keys", json={"name": "k"}).status_code == 401

        # Create a key via admin
        created = client.post(
            "/admin/keys", json={"name": "k"}, headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        assert created.status_code == 201
        api_key = created.json()["api_key"]
        key_id = created.json()["id"]

        auth = {"Authorization": f"Bearer {api_key}"}
        assert client.post("/v1/runs", json={"query": "x"}, headers=auth).status_code == 202

        # Key appears in the admin listing with usage metered
        listed = client.get("/admin/keys", headers={"X-Admin-Token": ADMIN_TOKEN}).json()
        assert any(k["id"] == key_id and k["request_count"] >= 1 for k in listed)

        # Revoke -> key rejected
        admin = {"X-Admin-Token": ADMIN_TOKEN}
        assert client.delete(f"/admin/keys/{key_id}", headers=admin).status_code == 204
        assert client.post("/v1/runs", json={"query": "x"}, headers=auth).status_code == 401


def test_open_mode_when_auth_disabled(tmp_path):
    app = make_app(tmp_path, auth_enabled=False)
    with TestClient(app) as client:
        assert client.post("/v1/runs", json={"query": "x"}).status_code == 202


def test_rate_limit_returns_429(tmp_path):
    app = make_app(tmp_path, rate_per_min=2)
    with TestClient(app) as client:
        created = client.post(
            "/admin/keys", json={"name": "rl"}, headers={"X-Admin-Token": ADMIN_TOKEN}
        )
        auth = {"Authorization": f"Bearer {created.json()['api_key']}"}
        codes = [
            client.post("/v1/runs", json={"query": "x"}, headers=auth).status_code
            for _ in range(3)
        ]
        assert codes[0] == 202
        assert codes[1] == 202
        assert codes[2] == 429


# --- MCP mount boot ------------------------------------------------------


def test_app_boots_with_mcp_mounted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key-for-boot")
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        # MCP is mounted at /mcp (streamable HTTP). A plain GET is not the right protocol call,
        # but it must reach the MCP app — i.e. NOT a 404 from the router.
        assert client.get("/mcp").status_code != 404

        # Hardening (M5): request tracing + CORS are wired on the real app.
        res = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert res.headers.get("X-Request-ID")
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"
