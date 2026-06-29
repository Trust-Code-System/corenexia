"""Eval-harness CI gate (Initiative B).

Runs the deterministic offline eval suite (fixture provider + real Docker sandbox) and asserts
the gate passes at 100%. Skipped automatically when Docker / the sandbox image is unavailable,
matching test_sandbox.py. This is the regression gate for the orchestration + evaluation path —
no API key, no LLM cost.
"""

from __future__ import annotations

import pytest

from app.sandbox.docker_runner import DockerRunner
from evals import run as evals_run

_ready, _message = DockerRunner().preflight()
pytestmark = pytest.mark.skipif(not _ready, reason=f"Docker sandbox unavailable: {_message}")


def test_offline_eval_gate_passes():
    report = evals_run.run(live=False, threshold=1.0)
    assert report.total >= 5  # legal + finance coverage
    failed = [t.id for t in report.tasks if not t.passed]
    assert report.gate_passed, f"offline eval gate failed for: {failed}"
    # Offline runs are free.
    assert report.total_cost_usd == 0.0


def test_evaluators_catch_a_wrong_answer():
    # A deliberately wrong fixture answer must fail its evaluators (proves the gate has teeth).
    bad_task = {
        "id": "sanity-wrong",
        "domain": "finance",
        "query": "Compute 2+2 and print JSON {\"v\": 4}.",
        "evaluators": [
            {"type": "step_json_close", "field": "v", "expected": 4, "tol": 0.01},
            {"type": "answer_contains", "values": ["four"]},
        ],
        "fixture": {"code": "import json; print(json.dumps({'v': 5}))", "answer": "It is five."},
    }
    report = evals_run.run(live=False, threshold=1.0, dataset=[bad_task])
    assert not report.gate_passed
    assert report.passed == 0
