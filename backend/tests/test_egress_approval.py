"""Dynamic-synthesis human-approval gate tests (Initiative D). No Docker, no internet.

The proxy test mutates the allowlist at runtime (an approval) and shows the live proxy starts
permitting a previously-blocked local host — proving the gate actually controls egress.
"""

from __future__ import annotations

import socket
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import admin_router
from app.llm.base import LLMProvider, LLMResult, Message, TextBlock, ToolUseBlock
from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.tools import REQUEST_EGRESS
from app.sandbox.egress import EgressPolicy, EgressProxy
from app.sandbox.egress_approval import APPROVED, DENIED, PENDING, EgressApprovalStore
from tests.test_egress import _EchoHandler, _EchoServer, _http_response_status
from tests.test_gateway import ADMIN_TOKEN
from tests.test_graph import FakeSandbox

# --- policy mutability ---------------------------------------------------


def test_policy_add_remove_hosts():
    p = EgressPolicy(["api.example.com"])
    assert p.is_allowed("api.example.com")
    p.add("data.example.org")
    p.add("*.cdn.net")
    assert p.is_allowed("data.example.org")
    assert p.is_allowed("x.cdn.net")
    assert set(p.hosts()) == {"api.example.com", "data.example.org", "*.cdn.net"}
    p.remove("data.example.org")
    assert not p.is_allowed("data.example.org")


# --- approval store ------------------------------------------------------


def test_request_pending_then_approve_adds_to_policy():
    policy = EgressPolicy()
    store = EgressApprovalStore(policy)

    req = store.request("api.vendor.com", "fetch prices")
    assert req.status == PENDING
    assert not policy.is_allowed("api.vendor.com")

    # duplicate request for the same host reuses the pending one
    assert store.request("api.vendor.com", "again").id == req.id

    approved = store.approve(req.id)
    assert approved.status == APPROVED
    assert policy.is_allowed("api.vendor.com")   # now on the live allowlist


def test_already_allowed_short_circuits_and_deny_blocks():
    policy = EgressPolicy(["ok.com"])
    store = EgressApprovalStore(policy)
    assert store.request("ok.com").status == APPROVED      # no human needed

    req = store.request("nope.com", "x")
    assert store.deny(req.id).status == DENIED
    assert not policy.is_allowed("nope.com")


# --- agent tool + graph dispatch -----------------------------------------


class RequestsEgressProvider(LLMProvider):
    name = "egress-req"

    def __init__(self):
        self.calls = 0
        self.tool_result: str | None = None

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            assert any(t.name == REQUEST_EGRESS.name for t in tools)
            assert "request_egress" in system
            call = ToolUseBlock(id="e1", name=REQUEST_EGRESS.name,
                                input={"host": "api.vendor.com", "reason": "prices"})
            return LLMResult(Message("assistant", [call]), tool_calls=[call],
                             stop_reason="tool_use")
        self.tool_result = messages[-1].blocks[0].content
        return LLMResult(Message("assistant", [TextBlock("ok")]), text="ok",
                         stop_reason="end_turn")


def test_agent_request_egress_files_pending():
    policy = EgressPolicy()
    store = EgressApprovalStore(policy)
    provider = RequestsEgressProvider()
    app = build_orchestrator(provider, FakeSandbox(stdout="x"), egress_approvals=store)

    run_orchestration(app, "Get vendor prices", max_iterations=4)

    assert "pending_approval" in provider.tool_result
    assert [r.host for r in store.list(PENDING)] == ["api.vendor.com"]


# --- admin endpoints + live proxy enforcement ----------------------------


def _admin_app() -> tuple[FastAPI, EgressPolicy, EgressApprovalStore]:
    policy = EgressPolicy()
    store = EgressApprovalStore(policy)
    app = FastAPI()
    app.state.admin_token = ADMIN_TOKEN
    app.state.egress_policy = policy
    app.state.egress_approvals = store
    app.include_router(admin_router)
    return app, policy, store


def test_admin_approve_unblocks_live_proxy():
    app, policy, store = _admin_app()
    admin = {"X-Admin-Token": ADMIN_TOKEN}

    # A local echo server stands in for an "external" host; block it at first.
    echo = _EchoServer(("127.0.0.1", 0), _EchoHandler)
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    echo_port = echo.server_address[1]
    proxy = EgressProxy(policy).start()

    try:
        # Agent files a request (simulated directly), proxy still blocks the host.
        req = store.request("127.0.0.1", "reach the service")
        b = socket.create_connection(proxy.address, timeout=5)
        b.sendall(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode())
        assert b"403" in _http_response_status(b)
        b.close()

        with TestClient(app) as client:
            # It shows up for review, then we approve it.
            listed = client.get("/admin/egress/requests", headers=admin).json()
            assert any(r["host"] == "127.0.0.1" and r["status"] == "pending" for r in listed)
            ok = client.post(f"/admin/egress/requests/{req.id}/approve", headers=admin)
            assert ok.status_code == 200 and ok.json()["status"] == "approved"
            allow = client.get("/admin/egress/allowlist", headers=admin).json()["hosts"]
            assert "127.0.0.1" in allow

        # Now the same CONNECT succeeds through the live proxy.
        c = socket.create_connection(proxy.address, timeout=5)
        c.sendall(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode())
        assert b"200" in _http_response_status(c)
        c.recv(4096)
        c.sendall(b"hello")
        assert c.recv(1024) == b"hello"
        c.close()
    finally:
        proxy.stop()
        echo.shutdown()
        echo.server_close()
