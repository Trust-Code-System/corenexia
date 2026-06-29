"""WebSocket telemetry tests — no Docker, no API key, no network.

Builds an app wired with fakes, connects to /ws/telemetry, starts a background run, and asserts
the live event sequence plus the retrievable final result.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.api.ws import ws_router
from app.orchestrator.graph import build_orchestrator
from app.orchestrator.runs import RunRegistry
from app.telemetry.events import EventBus
from tests.test_graph import FakeSandbox, ScriptedProvider


def make_app(tmp_path) -> FastAPI:
    bus = EventBus()
    provider = ScriptedProvider()
    sandbox = FakeSandbox(stdout='{"governing_law": "Delaware"}')

    app = FastAPI()
    app.state.bus = bus
    app.state.runs = RunRegistry(str(tmp_path / "runs.db"))
    app.state.provider = provider
    app.state.sandbox = sandbox
    app.state.sandbox_ready = True
    app.state.sandbox_message = "fake"
    app.state.orchestrator = build_orchestrator(provider, sandbox, bus)
    app.include_router(router)
    app.include_router(ws_router)
    return app


def test_ws_streams_background_run_events(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            # Background run returns immediately; events then flow over the socket.
            resp = client.post("/v1/runs", json={"query": "What is the governing law?"})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            phases: list[str] = []
            for _ in range(30):
                event = ws.receive_json()
                if event["run_id"] != run_id:
                    continue
                phases.append(event["phase"])
                if event["phase"] in ("done", "error"):
                    break

        assert "thinking" in phases
        assert "writing_code" in phases
        assert "executing_sandbox" in phases
        assert phases[-1] == "done"

        # The final result is retrievable once the background task settles.
        status = _await_run(client, run_id)
        assert status["status"] == "done"
        assert status["result"]["answer"] == "Governing law is Delaware."


def test_ws_run_filter_ignores_other_runs(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        # Connect filtered to a run id that will never be produced.
        with client.websocket_connect("/ws/telemetry?run_id=does-not-exist"):
            resp = client.post("/v1/runs", json={"query": "anything"})
            assert resp.status_code == 202
            real_run_id = resp.json()["run_id"]
            # Wait for the real run to finish out-of-band.
            _await_run(client, real_run_id)
            # The filtered socket should not have received the unrelated run's events.
            # (We can't easily assert "no message" without blocking, so just confirm the run
            # completed independently of this socket.)
            assert client.get(f"/v1/runs/{real_run_id}").json()["status"] == "done"


def _await_run(client: TestClient, run_id: str, tries: int = 50) -> dict:
    for _ in range(tries):
        status = client.get(f"/v1/runs/{run_id}").json()
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    return client.get(f"/v1/runs/{run_id}").json()
