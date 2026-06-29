"""DockerRunner integration tests. Skipped automatically if Docker / the image is unavailable.

Build the image first:  docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .
"""

from __future__ import annotations

import pytest

from app.sandbox.docker_runner import DockerRunner

runner = DockerRunner()
_ready, _message = runner.preflight()
pytestmark = pytest.mark.skipif(not _ready, reason=f"Docker sandbox unavailable: {_message}")


def test_basic_execution_captures_stdout():
    result = runner.run("print(2 + 2)")
    assert result.ok
    assert result.stdout.strip() == "4"


def test_network_is_isolated():
    # --network none means any outbound connection attempt must fail.
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "    print('NETWORK_REACHABLE')\n"
        "except OSError as e:\n"
        "    print('BLOCKED', type(e).__name__)\n"
    )
    result = runner.run(code)
    assert "NETWORK_REACHABLE" not in result.stdout
    assert "BLOCKED" in result.stdout


def test_infinite_loop_is_timed_out():
    result = runner.run("while True:\n    pass\n", timeout=5)
    assert result.timed_out
    assert result.exit_code == 124


def test_nonzero_exit_is_reported():
    result = runner.run("import sys; sys.exit(3)")
    assert not result.ok
    assert result.exit_code == 3
