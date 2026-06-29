"""Docker-backed sandbox: one hardened, ephemeral container per execution.

Security boundary for untrusted, AI-generated code. Each call runs a throwaway container with:
  - no network            (--network none)
  - capped memory + swap   (--memory / --memory-swap)
  - capped CPU and PIDs    (--cpus / --pids-limit)
  - read-only root + a small writable /tmp tmpfs
  - non-root user (nobody) (--user 65534:65534)
  - all Linux capabilities dropped + no privilege escalation
  - a wall-clock timeout that force-kills the container

Code is delivered over stdin (`python -`), so the common path needs no host bind mounts.
Optional input files are written to a temp dir and mounted read-only at /sandbox/files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from app.config import settings
from app.sandbox.base import SandboxResult, SandboxRunner

_TIMEOUT_EXIT_CODE = 124


class DockerRunner(SandboxRunner):
    def __init__(
        self,
        image: str | None = None,
        memory: str | None = None,
        cpus: float | None = None,
        pids_limit: int | None = None,
        default_timeout: int | None = None,
        max_concurrency: int | None = None,
        runtime: str | None = None,
        seccomp_profile: str | None = None,
        egress_enabled: bool | None = None,
        egress_proxy_url: str | None = None,
        egress_network: str | None = None,
    ):
        self.image = image or settings.sandbox_image
        self.memory = memory or settings.sandbox_memory
        self.cpus = cpus if cpus is not None else settings.sandbox_cpus
        self.pids_limit = pids_limit if pids_limit is not None else settings.sandbox_pids_limit
        self.default_timeout = default_timeout or settings.sandbox_timeout_seconds
        # OCI runtime: None/"docker" => Docker's default (runc); "runsc" => gVisor.
        self.runtime = runtime
        self.seccomp_profile = seccomp_profile or settings.sandbox_seccomp_profile
        # Egress: OFF by default → --network none. When enabled with a proxy URL, the container is
        # attached to `egress_network` and routed through the allowlist proxy (see egress.py).
        self.egress_enabled = (
            settings.sandbox_egress_enabled if egress_enabled is None else egress_enabled
        )
        self.egress_proxy_url = (
            settings.sandbox_egress_proxy_url if egress_proxy_url is None else egress_proxy_url
        )
        self.egress_network = egress_network or settings.sandbox_egress_network
        # Cap simultaneous containers so a burst of runs can't exhaust host resources.
        limit = max_concurrency if max_concurrency is not None else settings.sandbox_max_concurrency
        self._slots = threading.Semaphore(max(1, limit))

    def _network_args(self) -> list[str]:
        """Network flags. Default is full isolation; egress mode routes through the allowlist proxy.

        SECURITY: egress mode only enforces the allowlist if `egress_network` is locked down so the
        proxy is the container's only route out. Without a proxy URL we fail closed to no-network.
        """
        if not (self.egress_enabled and self.egress_proxy_url):
            return ["--network", "none"]  # no egress (exfiltration boundary) — the default
        proxy = self.egress_proxy_url
        return [
            "--network", self.egress_network,
            "-e", f"HTTP_PROXY={proxy}", "-e", f"http_proxy={proxy}",
            "-e", f"HTTPS_PROXY={proxy}", "-e", f"https_proxy={proxy}",
            "-e", "NO_PROXY=localhost,127.0.0.1", "-e", "no_proxy=localhost,127.0.0.1",
        ]

    def _security_opts(self) -> list[str]:
        """Hardening flags shared by every run."""
        opts = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        # Keep Docker's default seccomp filter unless explicitly overridden.
        if self.seccomp_profile and self.seccomp_profile != "default":
            opts += ["--security-opt", f"seccomp={self.seccomp_profile}"]
        if self.runtime and self.runtime not in ("docker", "runc"):
            opts += ["--runtime", self.runtime]
        return opts

    def preflight(self) -> tuple[bool, str]:
        try:
            version = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            return False, "Docker CLI not found on PATH. Install Docker and ensure it is running."
        except subprocess.TimeoutExpired:
            return False, "Docker daemon did not respond within 15s. Is Docker running?"

        if version.returncode != 0:
            return False, (
                f"Docker daemon not reachable: {version.stderr.strip()}. Is Docker running?"
            )

        image_check = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True,
            text=True,
        )
        if image_check.returncode != 0:
            return False, (
                f"Sandbox image '{self.image}' not found. Build it with: "
                f"docker build -t {self.image} -f docker/sandbox.Dockerfile ."
            )

        # If a non-default OCI runtime is requested (e.g. gVisor's runsc), confirm it's registered.
        if self.runtime and self.runtime not in ("docker", "runc"):
            info = subprocess.run(
                ["docker", "info", "--format", "{{json .Runtimes}}"],
                capture_output=True,
                text=True,
            )
            if self.runtime not in info.stdout:
                return False, (
                    f"Sandbox runtime '{self.runtime}' is not registered with Docker. "
                    f"Install gVisor (runsc) and add it to the daemon, or set "
                    f"SANDBOX_RUNTIME=docker. Available: {info.stdout.strip() or 'unknown'}."
                )

        runtime_note = f" runtime={self.runtime}" if self.runtime else ""
        return True, (
            f"Docker ready (server {version.stdout.strip()}); image '{self.image}' present"
            f"{runtime_note}."
        )

    def run(
        self,
        code: str,
        files: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        timeout = timeout or self.default_timeout
        name = f"corenexia-sbx-{uuid.uuid4().hex[:12]}"
        mount_dir: str | None = None

        cmd = [
            "docker", "run", "--rm", "-i",
            "--name", name,
            *self._network_args(),             # --network none by default; proxy if egress enabled
            "--memory", self.memory,
            "--memory-swap", self.memory,      # equal to --memory disables swap
            "--cpus", str(self.cpus),
            "--pids-limit", str(self.pids_limit),
            "--read-only",                     # immutable rootfs
            "--tmpfs", "/tmp:rw,size=64m,mode=1777",
            "--user", "65534:65534",           # non-root (nobody)
            *self._security_opts(),            # cap-drop ALL, no-new-privileges, seccomp, runtime
        ]

        if files:
            mount_dir = tempfile.mkdtemp(prefix="corenexia-sbx-")
            for filename, contents in files.items():
                safe_name = os.path.basename(filename)  # prevent path traversal
                if not safe_name or safe_name in (".", ".."):
                    continue
                with open(os.path.join(mount_dir, safe_name), "w", encoding="utf-8") as fh:
                    fh.write(contents)
            cmd += ["-v", f"{mount_dir}:/sandbox/files:ro"]

        cmd += [self.image, "python", "-"]

        start = time.monotonic()
        timed_out = False
        # Bound the number of containers running at once.
        self._slots.acquire()
        try:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Docker CLI not found on PATH. Install Docker and ensure it is running."
                ) from exc

            try:
                stdout, stderr = proc.communicate(input=code, timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                # Killing the `docker run` client does not stop the container — kill it by name.
                subprocess.run(["docker", "kill", name], capture_output=True, text=True)
                try:
                    stdout, stderr = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                exit_code = _TIMEOUT_EXIT_CODE
        finally:
            self._slots.release()
            if mount_dir:
                shutil.rmtree(mount_dir, ignore_errors=True)

        return SandboxResult(
            stdout=stdout or "",
            stderr=stderr or "",
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
