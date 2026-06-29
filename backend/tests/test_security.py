"""Security boundary tests — the isolation moat (Initiative A).

Docker-backed tests assert the sandbox actually contains untrusted code: no host secrets, no
egress, read-only rootfs, non-root, and enforced resource caps. They skip automatically if Docker
or the image is unavailable. The MCP-auth test needs no Docker.

Build the image first:  docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.auth import MCPAuthMiddleware
from app.gateway.keys import KeyStore
from app.sandbox.docker_runner import DockerRunner

runner = DockerRunner()
_ready, _message = runner.preflight()
docker_required = pytest.mark.skipif(not _ready, reason=f"Docker sandbox unavailable: {_message}")


# --- Isolation boundary (Docker) -----------------------------------------


@docker_required
def test_host_secrets_not_visible_in_sandbox():
    # A secret in the host process environment must NOT leak into the container.
    os.environ["CORENEXIA_TEST_SECRET"] = "leak-me-if-you-can"
    try:
        result = runner.run(
            "import os, json; print(json.dumps(sorted(os.environ.keys())))"
        )
    finally:
        os.environ.pop("CORENEXIA_TEST_SECRET", None)
    assert "leak-me-if-you-can" not in result.stdout
    assert "CORENEXIA_TEST_SECRET" not in result.stdout
    assert "ANTHROPIC_API_KEY" not in result.stdout


@docker_required
def test_runs_as_non_root():
    result = runner.run("import os; print(os.getuid())")
    assert result.ok
    assert result.stdout.strip() == "65534"  # nobody


@docker_required
def test_rootfs_is_read_only():
    result = runner.run("open('/evil.txt', 'w').write('x')")
    assert not result.ok  # read-only filesystem


@docker_required
def test_tmp_is_writable():
    result = runner.run("open('/tmp/ok.txt', 'w').write('hi'); print('wrote')")
    assert result.ok
    assert "wrote" in result.stdout


@docker_required
def test_no_network_egress():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
        "    print('REACHABLE')\n"
        "except OSError:\n"
        "    print('BLOCKED')\n"
    )
    result = runner.run(code)
    assert "REACHABLE" not in result.stdout
    assert "BLOCKED" in result.stdout


@docker_required
def test_memory_cap_is_enforced():
    # Allocating far beyond --memory triggers the cgroup OOM killer (non-zero exit).
    result = runner.run("x = bytearray(2 * 1024 * 1024 * 1024)  # 2 GiB\nprint(len(x))")
    assert not result.ok


# --- MCP endpoint auth (no Docker) ---------------------------------------


def _mcp_app(tmp_path, *, auth_enabled: bool):
    keys = KeyStore(str(tmp_path / "keys.db"))
    app = FastAPI()
    app.add_middleware(MCPAuthMiddleware)
    app.state.auth_enabled = auth_enabled
    app.state.keys = keys

    @app.get("/mcp/ping")
    async def mcp_ping() -> dict:
        return {"ok": True}

    @app.get("/open")
    async def open_route() -> dict:
        return {"ok": True}

    return app, keys


def test_mcp_requires_key_when_auth_enabled(tmp_path):
    app, keys = _mcp_app(tmp_path, auth_enabled=True)
    with TestClient(app) as client:
        assert client.get("/mcp/ping").status_code == 401
        raw, _ = keys.create("mcp-client")
        ok = client.get("/mcp/ping", headers={"Authorization": f"Bearer {raw}"})
        assert ok.status_code == 200
        # Non-MCP routes are unaffected by this middleware.
        assert client.get("/open").status_code == 200


def test_mcp_open_when_auth_disabled(tmp_path):
    app, _ = _mcp_app(tmp_path, auth_enabled=False)
    with TestClient(app) as client:
        assert client.get("/mcp/ping").status_code == 200
