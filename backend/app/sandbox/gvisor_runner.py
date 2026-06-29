"""gVisor sandbox runner.

gVisor (`runsc`) is an application kernel that intercepts syscalls in user space, giving much
stronger isolation than stock containers — the defense the 2026 MCP-security research recommends
for executing untrusted code ("containers alone proved insufficient"). Mechanically it's the
hardened Docker runner with Docker's `--runtime=runsc`, so we subclass DockerRunner.

Platform note: gVisor runs on Linux (deploy/CI/cloud). On Windows/macOS Docker Desktop, runsc is
typically unavailable — `preflight()` detects this and reports a clear message; use
SANDBOX_RUNTIME=docker locally.
"""

from __future__ import annotations

from app.sandbox.docker_runner import DockerRunner


class GvisorRunner(DockerRunner):
    def __init__(self, **kwargs):
        kwargs.setdefault("runtime", "runsc")
        super().__init__(**kwargs)
