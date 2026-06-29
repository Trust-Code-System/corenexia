"""Ephemeral code-execution sandbox. Docker now; E2B (Firecracker microVMs) later."""

from app.sandbox.base import SandboxResult, SandboxRunner


def build_sandbox() -> SandboxRunner:
    """Construct the configured sandbox runner (SANDBOX_RUNTIME: docker | gvisor | e2b)."""
    from app.config import settings

    runtime = settings.sandbox_runtime.lower()
    if runtime in ("docker", "runc"):
        from app.sandbox.docker_runner import DockerRunner

        return DockerRunner()
    if runtime in ("gvisor", "runsc"):
        from app.sandbox.gvisor_runner import GvisorRunner

        return GvisorRunner()
    if runtime == "e2b":
        from app.sandbox.e2b_runner import E2BRunner

        return E2BRunner()
    raise ValueError(
        f"Unknown SANDBOX_RUNTIME '{settings.sandbox_runtime}'. Use 'docker', 'gvisor', or 'e2b'."
    )


__all__ = ["SandboxResult", "SandboxRunner", "build_sandbox"]
