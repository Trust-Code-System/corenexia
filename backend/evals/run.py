"""Eval runner + CI gate.

Usage (from the `backend/` directory):

    python -m evals.run --offline            # deterministic gate (no LLM cost) — CI uses this
    python -m evals.run --live               # real model (spends money; user-gated)
    python -m evals.run --offline --threshold 1.0 --json report.json

Offline mode replays each task's fixture through the real Docker sandbox and grades the output.
Live mode runs the same dataset against the configured Anthropic model. Exit code is non-zero
when the pass rate is below the threshold, so CI fails on a regression.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.runs import final_to_result
from app.sandbox.docker_runner import DockerRunner
from evals.evaluators import EvalOutcome, evaluate
from evals.fixtures import FixtureProvider

DATASET_PATH = Path(__file__).parent / "dataset.json"


@dataclass
class TaskResult:
    id: str
    domain: str
    passed: bool
    outcomes: list[EvalOutcome]
    cost_usd: float
    status: str


@dataclass
class Report:
    mode: str
    total: int
    passed: int
    threshold: float
    pass_rate: float
    gate_passed: bool
    total_cost_usd: float
    tasks: list[TaskResult]


def load_dataset(path: Path = DATASET_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_one(task: dict, *, live: bool, sandbox: DockerRunner) -> TaskResult:
    if live:
        from app.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
    else:
        fx = task["fixture"]
        provider = FixtureProvider(code=fx["code"], answer=fx["answer"])

    orchestrator = build_orchestrator(provider, sandbox)
    final = run_orchestration(
        orchestrator, task["query"], task.get("context"), max_iterations=4
    )
    result = final_to_result(final)
    outcomes = evaluate(result, task["evaluators"])
    return TaskResult(
        id=task["id"],
        domain=task["domain"],
        passed=all(o.passed for o in outcomes),
        outcomes=outcomes,
        cost_usd=float((result.get("usage") or {}).get("cost_usd", 0.0)),
        status=result.get("status", ""),
    )


def run(*, live: bool = False, threshold: float = 1.0,
        dataset: list[dict] | None = None) -> Report:
    tasks = dataset if dataset is not None else load_dataset()
    sandbox = DockerRunner()  # shared across tasks; one ephemeral container per execution
    results = [_run_one(t, live=live, sandbox=sandbox) for t in tasks]

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pass_rate = (passed / total) if total else 0.0
    return Report(
        mode="live" if live else "offline",
        total=total,
        passed=passed,
        threshold=threshold,
        pass_rate=pass_rate,
        gate_passed=pass_rate >= threshold,
        total_cost_usd=round(sum(r.cost_usd for r in results), 6),
        tasks=results,
    )


def _print_report(report: Report) -> None:
    print(f"\nCorenexia evals — {report.mode} mode\n" + "=" * 48)
    for r in report.tasks:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.id} ({r.domain})  status={r.status}")
        for o in r.outcomes:
            if not o.passed:
                print(f"        - {o.name}: {o.detail}")
    print("-" * 48)
    print(f"Passed {report.passed}/{report.total} "
          f"(pass rate {report.pass_rate:.0%}, threshold {report.threshold:.0%})")
    if report.mode == "live":
        print(f"Total cost: ${report.total_cost_usd:.4f}")
    print("GATE:", "PASSED" if report.gate_passed else "FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corenexia eval harness")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true",
                      help="deterministic fixtures (default; no LLM cost)")
    mode.add_argument("--live", action="store_true",
                      help="run against the real model (spends money)")
    parser.add_argument("--threshold", type=float, default=1.0,
                        help="minimum pass rate to pass the gate (default 1.0)")
    parser.add_argument("--json", type=str, default=None,
                        help="write the full report JSON to this path")
    args = parser.parse_args(argv)

    sandbox = DockerRunner()
    ready, message = sandbox.preflight()
    if not ready:
        print(f"ERROR: sandbox not ready — {message}", file=sys.stderr)
        print("Build it: docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .",
              file=sys.stderr)
        return 2

    report = run(live=args.live, threshold=args.threshold)
    _print_report(report)
    if args.json:
        Path(args.json).write_text(json.dumps(_report_to_dict(report), indent=2), encoding="utf-8")
    return 0 if report.gate_passed else 1


def _report_to_dict(report: Report) -> dict:
    d = asdict(report)  # dataclasses (incl. nested EvalOutcome) serialize cleanly
    return d


if __name__ == "__main__":
    raise SystemExit(main())
