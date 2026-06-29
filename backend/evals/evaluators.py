"""Reusable evaluators for orchestration results.

An evaluator is a pure function `(result, spec) -> EvalOutcome`. `result` is the public run shape
(``answer``, ``steps``, ``status``, ``usage``); `spec` is the evaluator's JSON config from the
dataset. Evaluators are deterministic so they grade offline (fixture) and live runs identically.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalOutcome:
    name: str
    passed: bool
    detail: str = ""


def _last_step_json(result: dict) -> tuple[dict | None, str]:
    """Parse the last sandbox step's stdout as JSON. Returns (data_or_None, error_detail)."""
    steps = result.get("steps") or []
    if not steps:
        return None, "no sandbox steps to inspect"
    stdout = (steps[-1].get("stdout") or "").strip()
    try:
        return json.loads(stdout), ""
    except (ValueError, TypeError):
        return None, f"last step stdout is not JSON: {stdout[:120]!r}"


# --- evaluators ----------------------------------------------------------


def no_error(result: dict, spec: dict) -> EvalOutcome:
    steps = result.get("steps") or []
    bad = [s for s in steps if s.get("exit_code", 0) != 0 or s.get("timed_out")]
    ok = result.get("status") in {"done", "max_iterations"} and not bad
    detail = "" if ok else f"status={result.get('status')}, failed_steps={len(bad)}"
    return EvalOutcome("no_error", ok, detail)


def answer_contains(result: dict, spec: dict) -> EvalOutcome:
    answer = result.get("answer") or ""
    values: list[str] = spec.get("values", [])
    if spec.get("ignore_case"):
        haystack = answer.lower()
        needles = [v.lower() for v in values]
    else:
        haystack = answer
        needles = values
    mode = spec.get("mode", "all")  # "all" | "any"
    hits = [n for n in needles if n in haystack]
    passed = (len(hits) == len(needles)) if mode == "all" else bool(hits)
    missing = [v for v, n in zip(values, needles, strict=False) if n not in haystack]
    return EvalOutcome(
        f"answer_contains({mode})", passed, "" if passed else f"missing={missing}"
    )


def answer_regex(result: dict, spec: dict) -> EvalOutcome:
    answer = result.get("answer") or ""
    pattern = spec["pattern"]
    flags = re.IGNORECASE if spec.get("ignore_case") else 0
    passed = re.search(pattern, answer, flags) is not None
    return EvalOutcome("answer_regex", passed, "" if passed else f"no match for /{pattern}/")


def step_json_field(result: dict, spec: dict) -> EvalOutcome:
    """Assert a field in the last step's JSON stdout equals an expected value (exact)."""
    data, err = _last_step_json(result)
    field = spec["field"]
    if data is None:
        return EvalOutcome(f"step_json_field({field})", False, err)
    actual = data.get(field)
    expected = spec["equals"]
    passed = actual == expected
    return EvalOutcome(
        f"step_json_field({field})", passed,
        "" if passed else f"expected {expected!r}, got {actual!r}",
    )


def step_json_close(result: dict, spec: dict) -> EvalOutcome:
    """Assert a numeric field in the last step's JSON is within tolerance of expected."""
    data, err = _last_step_json(result)
    field = spec["field"]
    if data is None:
        return EvalOutcome(f"step_json_close({field})", False, err)
    expected = float(spec["expected"])
    tol = float(spec.get("tol", 1e-6))
    try:
        actual = float(data.get(field))
    except (TypeError, ValueError):
        return EvalOutcome(
            f"step_json_close({field})", False, f"field not numeric: {data.get(field)!r}"
        )
    passed = abs(actual - expected) <= tol
    return EvalOutcome(
        f"step_json_close({field})", passed,
        "" if passed else f"expected {expected}±{tol}, got {actual}",
    )


REGISTRY: dict[str, Callable[[dict, dict], EvalOutcome]] = {
    "no_error": no_error,
    "answer_contains": answer_contains,
    "answer_regex": answer_regex,
    "step_json_field": step_json_field,
    "step_json_close": step_json_close,
}


def evaluate(result: dict, specs: list[dict[str, Any]]) -> list[EvalOutcome]:
    """Run every evaluator spec against a result. Unknown types fail loudly."""
    outcomes: list[EvalOutcome] = []
    for spec in specs:
        fn = REGISTRY.get(spec["type"])
        if fn is None:
            outcomes.append(EvalOutcome(spec["type"], False, "unknown evaluator type"))
            continue
        outcomes.append(fn(result, spec))
    return outcomes
