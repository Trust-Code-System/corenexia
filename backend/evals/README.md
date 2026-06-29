# Corenexia eval harness

A curated **legal + finance** task dataset, reusable evaluators, and a runner that scores the
orchestrator against thresholds as a **CI gate**.

## Run it

From the `backend/` directory (Docker must be running; build the sandbox image first):

```bash
docker build -t corenexia-sandbox -f ../docker/sandbox.Dockerfile ..

# Deterministic gate — no API key, no LLM cost. This is what CI runs.
python -m evals.run --offline

# Real model — spends money (uses ANTHROPIC_API_KEY). User-gated.
python -m evals.run --live

# Options
python -m evals.run --offline --threshold 0.9 --json report.json
```

Exit code is non-zero when the pass rate is below `--threshold` (default `1.0`), so CI fails on a
regression.

## How offline mode works

Each task carries a **fixture**: the exact Python the agent "would have written" plus the final
answer it "would have given". In offline mode a `FixtureProvider` replays those instead of calling
the model — but the code still runs in the **real Docker sandbox**, and the **real evaluators**
grade the output. So the offline gate genuinely exercises the execute→result→score path
deterministically and for free; only `--live` calls the model.

## Dataset (`dataset.json`)

Each task:

```jsonc
{
  "id": "finance-pe-ratio",
  "domain": "finance",                 // legal | finance
  "query": "…",                        // the task prompt
  "context": "…",                      // optional supporting text (e.g. a clause)
  "evaluators": [ { "type": "…", … } ],// graded against the result
  "fixture": { "code": "…", "answer": "…" }  // offline replay
}
```

## Evaluators (`evaluators.py`)

| type | checks |
|---|---|
| `no_error` | run finished and no sandbox step errored/timed out |
| `answer_contains` | answer includes `values` (`mode`: `all`/`any`, `ignore_case`) |
| `answer_regex` | answer matches `pattern` (`ignore_case`) |
| `step_json_field` | last step's JSON stdout has `field` == `equals` (exact) |
| `step_json_close` | last step's JSON `field` within `tol` of numeric `expected` |

Add a new evaluator by writing a `(result, spec) -> EvalOutcome` function and registering it in
`REGISTRY`. The same evaluators grade offline and live runs identically.

## Adding a task

Append an object to `dataset.json` with at least one evaluator and a fixture. Keep fixtures
honest — the fixture code should actually compute the answer (it runs in the sandbox), not just
print a constant, so the offline gate has real teeth.
