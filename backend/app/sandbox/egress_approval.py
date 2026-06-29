"""Human-approval gate for dynamic outbound domains (Initiative D).

When the orchestrator synthesizes an integration that needs to reach a host **not** already on the
egress allowlist, it does not get to open that connection itself. Instead it files an
**approval request** via the `request_egress` tool; a human reviews it (`/admin/egress/requests`)
and approves or denies. On approval the host is added to the live `EgressPolicy`, so — and only
then — the egress proxy will permit it. This keeps "the agent invents an integration" safe:
every new outbound domain is gated by a person.

The store is in-process with an audit list of decisions; pair it with the egress proxy
(`app/sandbox/egress.py`) which enforces the allowlist.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass

from app.sandbox.egress import EgressPolicy

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"


@dataclass
class EgressRequest:
    id: str
    host: str
    reason: str
    status: str
    requested_at: float
    decided_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EgressApprovalStore:
    """Tracks pending/decided egress requests and applies approvals to the live policy."""

    def __init__(self, policy: EgressPolicy):
        self._policy = policy
        self._requests: dict[str, EgressRequest] = {}
        self._lock = threading.Lock()

    def request(self, host: str, reason: str = "") -> EgressRequest:
        """File (or short-circuit) a request to reach `host`.

        Returns an APPROVED pseudo-request immediately if the host is already allowed; reuses an
        existing PENDING request for the same host instead of duplicating it.
        """
        host = (host or "").strip().lower()
        if not host:
            raise ValueError("A host is required.")
        if self._policy.is_allowed(host):
            return EgressRequest(
                id="(already-allowed)", host=host, reason=reason,
                status=APPROVED, requested_at=time.time(), decided_at=time.time(),
            )
        with self._lock:
            for req in self._requests.values():
                if req.host == host and req.status == PENDING:
                    return req
            req = EgressRequest(
                id=uuid.uuid4().hex[:12], host=host, reason=reason,
                status=PENDING, requested_at=time.time(),
            )
            self._requests[req.id] = req
            return req

    def list(self, status: str | None = None) -> list[EgressRequest]:
        with self._lock:
            reqs = sorted(self._requests.values(), key=lambda r: r.requested_at, reverse=True)
        return [r for r in reqs if status is None or r.status == status]

    def get(self, request_id: str) -> EgressRequest | None:
        with self._lock:
            return self._requests.get(request_id)

    def approve(self, request_id: str) -> EgressRequest | None:
        """Approve a pending request and add its host to the live egress allowlist."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None or req.status != PENDING:
                return req
            req.status = APPROVED
            req.decided_at = time.time()
        self._policy.add(req.host)  # outside the lock; EgressPolicy has its own lock
        return req

    def deny(self, request_id: str) -> EgressRequest | None:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None or req.status != PENDING:
                return req
            req.status = DENIED
            req.decided_at = time.time()
            return req
