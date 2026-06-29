"""Milestone 5 hardening tests — CORS, request tracing, run persistence, WebSocket auth.

No Docker or live API calls. The CORS/request-id checks boot the real app with a dummy key.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.ws import ws_router
from app.gateway.keys import KeyStore
from app.orchestrator.runs import RunRegistry
from app.telemetry.events import EventBus

# --- Observability: request id + CORS middleware -------------------------
# (The real app is booted once in test_gateway::test_app_boots_with_mcp_mounted, which also
# asserts these headers end-to-end. The MCP session manager is a module-level singleton that
# can only run once per process, so we exercise the middleware here on a minimal app.)


def test_request_id_and_cors_middleware():
    from fastapi.middleware.cors import CORSMiddleware

    from app.observability import RequestIDMiddleware

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        res = client.get("/ping", headers={"Origin": "http://localhost:3000"})
        assert res.status_code == 200
        assert res.headers.get("X-Request-ID")
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


# --- Run persistence: survives a new registry instance -------------------


def test_runs_persist_across_instances(tmp_path):
    db = str(tmp_path / "runs.db")
    reg = RunRegistry(db)
    record = reg.create("audit me")
    reg.finish(
        record.run_id,
        "done",
        {"run_id": record.run_id, "status": "done", "answer": "ok", "iterations": 1, "steps": []},
    )

    # A fresh registry pointed at the same file still sees the finished run.
    reg2 = RunRegistry(db)
    loaded = reg2.get(record.run_id)
    assert loaded is not None
    assert loaded.status == "done"
    assert loaded.result["answer"] == "ok"
    assert reg2.get("nonexistent") is None


# --- WebSocket auth ------------------------------------------------------


def _ws_app(tmp_path, *, auth_enabled: bool) -> tuple[FastAPI, KeyStore]:
    keys = KeyStore(str(tmp_path / "keys.db"))
    app = FastAPI()
    app.state.bus = EventBus()
    app.state.auth_enabled = auth_enabled
    app.state.keys = keys
    app.include_router(ws_router)
    return app, keys


def test_ws_rejected_without_key_when_auth_enabled(tmp_path):
    app, _ = _ws_app(tmp_path, auth_enabled=True)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/telemetry"):
                pass


def test_ws_accepts_valid_key(tmp_path):
    app, keys = _ws_app(tmp_path, auth_enabled=True)
    raw, _ = keys.create("ws-key")
    with TestClient(app) as client:
        # A valid key in the query param is accepted; entering/exiting closes cleanly.
        with client.websocket_connect(f"/ws/telemetry?api_key={raw}"):
            pass


def test_ws_open_when_auth_disabled(tmp_path):
    app, _ = _ws_app(tmp_path, auth_enabled=False)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry"):
            pass
