"""Egress allowlist proxy (Initiative A follow-up; pairs with Initiative D dynamic synthesis).

The sandbox runs with **no network by default**. The moment any outbound is required (e.g. a
synthesized API client), traffic must go through an **allowlist proxy** — never raw `--network`.
This module provides:

  * `EgressPolicy` — an allowlist of hosts (exact or `*.suffix` wildcard); empty = deny all.
  * `EgressProxy` — a small filtering forward proxy (HTTP `CONNECT` tunneling + absolute-form HTTP)
    that permits connections only to allowlisted hosts and returns `403` for everything else.

The proxy is the *policy* layer. In a real deployment the sandbox container is attached to a
locked-down network whose only route out is this proxy (so generated code cannot bypass it); on
Windows/macOS Docker Desktop this confinement is a deployment concern — see SECURITY.md.
"""

from __future__ import annotations

import logging
import select
import socket
import socketserver
import threading

from app.config import settings

logger = logging.getLogger("corenexia.egress")

_TUNNEL_BUF = 65536
_CONNECT_TIMEOUT = 10


class EgressPolicy:
    """Allowlist of hostnames. Supports exact matches and `*.example.com` wildcards."""

    def __init__(self, allowlist: list[str] | None = None):
        self._exact: set[str] = set()
        self._suffixes: list[str] = []
        for entry in allowlist or []:
            entry = entry.strip().lower()
            if not entry:
                continue
            if entry.startswith("*."):
                self._suffixes.append(entry[1:])  # ".example.com"
            else:
                self._exact.add(entry)

    @property
    def is_empty(self) -> bool:
        return not self._exact and not self._suffixes

    def is_allowed(self, host: str) -> bool:
        if not host:
            return False
        host = host.strip().lower().rstrip(".")
        if host in self._exact:
            return True
        return any(host.endswith(suffix) for suffix in self._suffixes)


def build_egress_policy() -> EgressPolicy:
    return EgressPolicy(settings.sandbox_egress_allowlist_list)


class _ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        policy: EgressPolicy = self.server.policy  # type: ignore[attr-defined]
        try:
            raw = self._read_headers()
        except OSError:
            return
        if not raw:
            return
        request_line = raw.split(b"\r\n", 1)[0].decode("latin-1").strip()
        parts = request_line.split()
        if len(parts) < 2:
            return
        method, target = parts[0].upper(), parts[1]
        if method == "CONNECT":
            self._handle_connect(target, policy)
        else:
            # Absolute-form HTTP (e.g. "GET http://host/path"): extract host, enforce.
            self._handle_http(method, target, policy)

    def _read_headers(self) -> bytes:
        """Read the full request header block (up to and including the terminating blank line)."""
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 16384:
                break
        return data

    def _deny(self, reason: str) -> None:
        body = f"Egress blocked by allowlist: {reason}".encode()
        self.request.sendall(
            b"HTTP/1.1 403 Forbidden\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )

    def _handle_connect(self, target: str, policy: EgressPolicy) -> None:
        host, _, port_s = target.partition(":")
        port = int(port_s) if port_s.isdigit() else 443
        if not policy.is_allowed(host):
            logger.warning("egress DENY CONNECT %s", host)
            self._deny(host)
            return
        try:
            upstream = socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT)
        except OSError as exc:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            logger.info("egress upstream connect failed %s:%s — %s", host, port, exc)
            return
        # The full CONNECT request (incl. blank line) was already consumed, so the tunnel is clean.
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        logger.info("egress ALLOW CONNECT %s:%s", host, port)
        self._tunnel(self.request, upstream)

    def _handle_http(self, method: str, target: str, policy: EgressPolicy) -> None:
        # Absolute-form: http://host[:port]/path
        host = ""
        if "://" in target:
            rest = target.split("://", 1)[1]
            hostport = rest.split("/", 1)[0]
            host = hostport.split(":", 1)[0]
        if not policy.is_allowed(host):
            logger.warning("egress DENY %s %s", method, host or target)
            self._deny(host or "unknown host")
            return
        # Minimal pass-through is out of scope for the default build; deny non-CONNECT for safety.
        self._deny("only HTTPS CONNECT egress is supported")

    @staticmethod
    def _tunnel(client: socket.socket, upstream: socket.socket) -> None:
        sockets = [client, upstream]
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 30)
                if exceptional or not readable:
                    break
                for s in readable:
                    other = upstream if s is client else client
                    data = s.recv(_TUNNEL_BUF)
                    if not data:
                        return
                    other.sendall(data)
        except OSError:
            pass
        finally:
            for s in (client, upstream):
                try:
                    s.close()
                except OSError:
                    pass


class _ThreadingProxyServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, policy: EgressPolicy):
        super().__init__(addr, _ProxyHandler)
        self.policy = policy


class EgressProxy:
    """A filtering forward proxy. Point sandbox HTTP(S)_PROXY at it; the allowlist is enforced."""

    def __init__(self, policy: EgressPolicy, host: str = "127.0.0.1", port: int = 0):
        self.policy = policy
        self._server = _ThreadingProxyServer((host, port), policy)
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address  # (host, port) — port resolved if 0 was requested

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    def start(self) -> EgressProxy:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)
