"""SandboxRunner interface. Implementations execute untrusted code in throwaway isolation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxRunner(ABC):
    """Runs a Python script in an isolated, ephemeral environment and returns its output."""

    @abstractmethod
    def run(
        self,
        code: str,
        files: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        """Execute `code` (Python 3.11). `files` maps filename -> text contents to make
        available to the script. The environment is destroyed after the call returns."""
        raise NotImplementedError

    def preflight(self) -> tuple[bool, str]:
        """Return (ready, message). Default: always ready."""
        return True, "ok"
