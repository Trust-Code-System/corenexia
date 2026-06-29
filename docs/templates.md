# Template packs

Corenexia ships ready-to-run task templates so a new install is useful immediately — and to
demonstrate the **general engine + vertical templates** model. There are three packs:

| Pack | Domain | Examples |
|---|---|---|
| **Legal** | `legal` | contract key-terms extraction · NDA triage (GREEN/YELLOW/RED) · compliance checklist |
| **Finance** | `finance` | equity valuation metrics · growth & CAGR · portfolio allocation breakdown |
| **General** | `general` | summarize tabular data · structured extraction from text · ad-hoc calculation |

## Discover them

```bash
curl http://localhost:8000/v1/templates                # all
curl "http://localhost:8000/v1/templates?domain=legal" # filtered
curl http://localhost:8000/v1/templates/packs          # pack summaries
curl http://localhost:8000/v1/templates/finance-equity-metrics
```

Each template:

```jsonc
{
  "id": "legal-nda-triage",
  "title": "NDA triage (GREEN / YELLOW / RED)",
  "description": "Screen an incoming NDA and classify its risk…",
  "query": "Review the NDA in the context. Identify the term length…",
  "domain": "legal",
  "pack": "legal",
  "tags": ["nda", "triage", "risk"],
  "example_context": "MUTUAL NON-DISCLOSURE AGREEMENT. …"
}
```

## Use one

A template is just a starting `query` (+ optional `example_context`). Run it like any task:

```bash
TPL=$(curl -s http://localhost:8000/v1/templates/finance-growth-cagr)
curl -X POST http://localhost:8000/v1/orchestrate -H 'Content-Type: application/json' \
  -d "$(echo "$TPL" | jq '{query, context: .example_context}')"
```

In the **God View**, the composer's *Starter template* dropdown loads any template (grouped by
domain) into the task + context fields with one click.

## Add your own

Templates are static JSON in [`backend/app/templates/packs/`](../backend/app/templates/packs/).
Add an object to a pack's `templates` array (or add a new `*.json` pack with `id`, `domain`,
`title`, `description`, `templates`). Template ids must be globally unique — the registry enforces
it at load time. No code change or restart logic beyond reloading the app.
