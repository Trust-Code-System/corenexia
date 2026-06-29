"""E2B (Firecracker microVM) runner — future seam.

E2B boots a true microVM in ~150ms, giving stronger isolation than a container and removing the
need for Docker on the host. Implementing this means installing the `e2b` SDK, creating a
sandbox, writing the script, running it, collecting stdout/stderr, and closing the sandbox.
Kept as a stub so DockerRunner can be swapped out with no change to the orchestrator.
"""

from __future__ import annotations

from app.sandbox.base import SandboxResult, SandboxRunner


class E2BRunner(SandboxRunner):
    def run(
        self,
        code: str,
        files: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        raise NotImplementedError(
            "E2BRunner is a placeholder for a later milestone. Use DockerRunner (build_sandbox())."
        )

    def preflight(self) -> tuple[bool, str]:
        return False, "E2BRunner not implemented; use DockerRunner."
