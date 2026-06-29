# Contributing to Corenexia

Thanks for your interest in Corenexia — the open, self-hostable Infinite Dynamic Orchestrator.
Contributions of all kinds are welcome: bug reports, docs, template packs, evaluators, and code.

## Ground rules

- Corenexia executes **untrusted, AI-generated code**. Anything that touches the sandbox boundary,
  the gateway, or egress is **security-sensitive** — call it out explicitly in your PR and add a
  test. When in doubt, read [SECURITY.md](SECURITY.md) first.
- Keep the scope tight. Domain is **legal** and **general finance** (no cryptocurrency).
- Don't commit secrets. `.env` / `backend/.env` are git-ignored; never bake keys into images.

## Dev setup

```bash
# Sandbox image (needed for sandbox + eval tests)
docker build -t corenexia-sandbox -f docker/sandbox.Dockerfile .

# Backend
python -m venv .venv && pip install -U -r backend/requirements.txt
# Frontend
cd frontend && npm install
```

See [docs/quickstart.md](docs/quickstart.md) for the full walkthrough.

## Before you open a PR — the local gates

These mirror CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)). All must pass:

```bash
cd backend
../.venv/Scripts/python.exe -m ruff check .          # lint (must be clean)
../.venv/Scripts/python.exe -m pytest -q             # all tests green
../.venv/Scripts/python.exe -m evals.run --offline   # eval gate (deterministic, no LLM cost)
cd ../frontend && npm run build                      # typecheck + build
```

- **Tests:** add/extend tests for any behavior change. The sandbox, security, and eval suites skip
  automatically when Docker is unavailable — run them with Docker before submitting.
- **No live LLM calls in tests.** Use the scripted/fixture providers (see `tests/test_graph.py`,
  `backend/evals/fixtures.py`). Live evals (`--live`) are opt-in and cost money.
- **Style:** match the surrounding code; `ruff` enforces `E,F,I,UP,B`. Keep functions small and
  comments purposeful.

## Good first contributions

- **Template packs** — add a task to `backend/app/templates/packs/*.json` (legal/finance/general).
  Ids must be globally unique. See [docs/templates.md](docs/templates.md).
- **Evaluators / eval tasks** — add a `(result, spec) -> EvalOutcome` evaluator or a dataset task
  in `backend/evals/`. See [backend/evals/README.md](backend/evals/README.md).
- **Docs** — clarify the quickstart, API reference, or security pages.

## Commit & PR

- Branch off `main`; keep PRs focused and described (what, why, how verified).
- Reference related issues. Note any security implications and the gates you ran.
- By contributing you agree your work is licensed under [Apache-2.0](LICENSE).

## Reporting vulnerabilities

Please **do not** open public issues for undisclosed vulnerabilities — follow the private
disclosure process in [SECURITY.md](SECURITY.md).
