"""Egress allowlist proxy tests (Initiative A follow-up). No Docker, no internet.

The CONNECT test tunnels to a *local* echo server (allowlisted), so it's deterministic and
offline. Also checks that the DockerRunner keeps --network none by default and only switches to the
proxy path when egress is explicitly enabled.
"""

from __future__ import annotations

import socket
import socketserver
import threading

from app.sandbox.docker_runner import DockerRunner
from app.sandbox.egress import EgressPolicy, EgressProxy

# --- policy units --------------------------------------------------------


def test_policy_deny_by_default():
    assert EgressPolicy().is_empty
    assert EgressPolicy().is_allowed("example.com") is False


def test_policy_exact_and_wildcard():
    p = EgressPolicy(["api.anthropic.com", "*.githubusercontent.com"])
    assert p.is_allowed("api.anthropic.com")
    assert p.is_allowed("API.Anthropic.com")            # case-insensitive
    assert p.is_allowed("raw.githubusercontent.com")    # wildcard suffix
    assert p.is_allowed("sub.raw.githubusercontent.com")
    assert not p.is_allowed("anthropic.com")            # not the exact host
    assert not p.is_allowed("evil.com")
    assert not p.is_allowed("githubusercontent.com.evil.com")


# --- proxy CONNECT tunneling (local) -------------------------------------


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(1024)
            if not data:
                return
            self.request.sendall(data)


class _EchoServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _http_response_status(sock: socket.socket) -> bytes:
    data = b""
    while b"\r\n" not in data:
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
    return data


def test_proxy_allows_listed_host_and_blocks_others():
    echo = _EchoServer(("127.0.0.1", 0), _EchoHandler)
    threading.Thread(target=echo.serve_forever, daemon=True).start()
    echo_port = echo.server_address[1]

    proxy = EgressProxy(EgressPolicy(["127.0.0.1"])).start()
    try:
        # Allowed: CONNECT to the local echo server tunnels through.
        c = socket.create_connection(proxy.address, timeout=5)
        c.sendall(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode())
        status = _http_response_status(c)
        assert b"200" in status
        # read the rest of the proxy's response headers (blank line) before tunneling data
        c.recv(4096)
        c.sendall(b"ping-through-tunnel")
        assert c.recv(1024) == b"ping-through-tunnel"
        c.close()

        # Blocked: CONNECT to a non-allowlisted host is refused with 403.
        b = socket.create_connection(proxy.address, timeout=5)
        b.sendall(b"CONNECT evil.example.com:443 HTTP/1.1\r\nHost: evil.example.com\r\n\r\n")
        assert b"403" in _http_response_status(b)
        b.close()
    finally:
        proxy.stop()
        echo.shutdown()
        echo.server_close()


# --- runner network args -------------------------------------------------


def test_runner_default_is_network_none():
    runner = DockerRunner(egress_enabled=False)
    assert runner._network_args() == ["--network", "none"]


def test_runner_egress_routes_through_proxy():
    runner = DockerRunner(
        egress_enabled=True,
        egress_proxy_url="http://host.docker.internal:8888",
        egress_network="corenexia-egress",
    )
    args = runner._network_args()
    assert "none" not in args
    assert "corenexia-egress" in args
    joined = " ".join(args)
    assert "HTTP_PROXY=http://host.docker.internal:8888" in joined
    assert "HTTPS_PROXY=http://host.docker.internal:8888" in joined


def test_runner_egress_fails_closed_without_proxy_url():
    # Enabled but no proxy URL → must NOT open the network; falls back to none.
    runner = DockerRunner(egress_enabled=True, egress_proxy_url="")
    assert runner._network_args() == ["--network", "none"]
