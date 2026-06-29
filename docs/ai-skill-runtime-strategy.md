# Corenexia AI Skill Runtime Strategy

This document captures the larger product direction for Corenexia after the current roadmap is finished. The immediate plan should remain:

1. Finish the existing Corenexia roadmap.
2. Verify the current backend, sandbox, frontend, MCP, auth, observability, templates, and deployment paths.
3. Then expand Corenexia from a legal/finance-focused orchestrator into a wider AI Skill Runtime.

The core idea is that Corenexia should not stay limited to legal contracts, finance calculations, or document analysis. Those are useful starter domains, but the bigger opportunity is to make Corenexia the runtime where AI systems can discover, install, compose, and safely execute skills.

## Executive Summary

Corenexia should become:

> An open, self-hostable AI Skill Runtime where ChatGPT, Claude, Codex, agents, applications, and internal company tools can discover, install, run, audit, and reuse executable skills safely.

In simpler terms:

> Corenexia is the safe execution layer for AI agents.

The current project already has many of the hard foundations:

- FastAPI backend.
- LangGraph orchestration loop.
- Docker/gVisor sandbox boundary.
- MCP server.
- REST API.
- WebSocket telemetry.
- Visual God View.
- API keys.
- rate limits.
- token/cost metering.
- spend caps.
- OpenTelemetry tracing.
- eval harness.
- template packs.
- Docker Compose packaging.

The next strategic step is to turn the current "orchestrator that writes and runs Python" into a broader runtime for reusable skills.

## Current Product Shape

Today, Corenexia is best described as:

> A self-hostable dynamic orchestrator that lets an LLM write Python on demand, execute it inside a hardened sandbox, and return structured results through REST, MCP, and a visual dashboard.

The current flagship domains are:

- legal contract analysis.
- NDA triage.
- compliance checks.
- equity and valuation calculations.
- CAGR and growth math.
- portfolio analysis.
- general extraction and tabular data summaries.

That is a good MVP because it gives concrete examples. But it is not the largest version of the product.

The larger version is not "AI for contracts." It is:

> A runtime for AI-executable skills.

## Larger Product Vision

The long-term product should be built around this idea:

> Any AI assistant should be able to ask Corenexia for the right skill, run that skill safely, inspect the result, and reuse or improve that skill later.

That means Corenexia becomes a bridge between:

- AI assistants.
- GitHub repositories.
- MCP servers.
- Python scripts.
- internal company tools.
- documents and data.
- workflow automation.
- sandboxed execution.
- audit logs.

The product should answer these questions:

- What skill can solve this task?
- Is the skill trusted?
- What permissions does it need?
- Where did the skill come from?
- Has it passed tests?
- Can it run safely?
- What did it do?
- What did it cost?
- Can this successful run become a reusable skill?

## Positioning

Do not lead with:

> Infinite Dynamic Orchestrator for legal and finance.

That sounds narrow and abstract.

A stronger broad positioning is:

> Corenexia is an open AI Skill Runtime. It lets AI assistants discover, install, and safely run skills from GitHub, MCP servers, and private registries inside hardened sandboxes.

Shorter options:

- The open runtime for AI-executable skills.
- Safe code execution and skill discovery for AI agents.
- A self-hostable skill layer for ChatGPT, Claude, Codex, and AI apps.
- Docker Hub plus GitHub Actions-style execution, but for AI skills.

The strongest product claim is:

> Corenexia turns AI-generated one-off code into trusted, reusable, auditable skills.

## Why This Can Matter

ChatGPT, Claude, Codex, and other AI systems are powerful, but they still need reliable tools. Users do not want every task solved from scratch every time. They want:

- repeatable workflows.
- safe execution.
- auditability.
- permissions.
- trusted tool sources.
- reusable capabilities.
- private deployment.
- integration with their own repos and data.

Corenexia can sit underneath AI products as the execution and skill layer.

AI models can reason, but they still need tools. Corenexia can be where those tools live, run, and get governed.

## Will ChatGPT, Claude, And Other AIs Use It?

They can use it if Corenexia is exposed through the right interfaces.

The main path is MCP.

OpenAI supports remote MCP servers through the Responses API and ChatGPT Apps. Claude also supports MCP server connections through its ecosystem. Other agent frameworks are moving in the same direction.

That means Corenexia does not need to be built separately for every AI. It should become a high-quality MCP server and API platform.

But AIs will not discover it automatically. Corenexia must be:

- deployed on HTTPS.
- compliant with MCP transport expectations.
- authenticated correctly.
- documented clearly.
- packaged for registry listing.
- easy to connect from AI clients.
- trusted by users and organizations.

The goal should be:

> If an AI host supports MCP, it should be able to call Corenexia.

## Will Users Use It?

Users will use it if the product is framed around outcomes, not infrastructure.

"AI Skill Runtime" is the platform category, but the demos should be concrete:

- analyze a repo and generate a risk report.
- pull a GitHub skill and run it safely.
- parse a PDF and produce structured JSON.
- run a company-approved spreadsheet validation skill.
- convert a successful AI-generated script into a reusable skill.
- let Claude or ChatGPT call a private Corenexia skill through MCP.

The likely early users are:

- AI builders.
- software teams.
- platform engineering teams.
- data analysts.
- automation engineers.
- security-conscious companies.
- legal ops teams.
- finance teams.
- compliance teams.
- technical founders.

The casual consumer market is weaker. Casual users already have ChatGPT and Claude. Corenexia becomes valuable when the user needs:

- repeatability.
- private deployment.
- safe execution.
- audit logs.
- reusable skills.
- GitHub/imported skill support.
- enterprise controls.

## Product Pillars

### 1. Universal Skill System

Skills should become the main product unit.

A skill can be:

- a Python script.
- a repo folder.
- a command-line wrapper.
- an MCP server wrapper.
- a workflow.
- a prompt plus code bundle.
- a document parser.
- a data analysis routine.
- an API integration.
- a browser automation.
- a reusable generated script.

Each skill should have a manifest.

Example:

```json
{
  "name": "repo-risk-scanner",
  "version": "0.1.0",
  "description": "Scans a source repo for risky patterns and produces a structured report.",
  "domains": ["software", "security"],
  "entrypoint": "skill.py",
  "input_schema": {
    "type": "object",
    "properties": {
      "repo_path": { "type": "string" }
    },
    "required": ["repo_path"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "summary": { "type": "string" },
      "findings": { "type": "array" }
    }
  },
  "permissions": {
    "network": false,
    "filesystem": "readonly"
  },
  "dependencies": []
}
```

The manifest should define:

- name.
- version.
- description.
- domains.
- entrypoint.
- inputs.
- outputs.
- dependencies.
- permissions.
- examples.
- tests.
- trust metadata.

### 2. GitHub Skill Import

The user wants Corenexia to pull GitHub project skills. This should be implemented as a controlled import pipeline, not as random repo execution.

The user should be able to paste:

```text
https://github.com/org/repo
```

or:

```text
https://github.com/org/repo/tree/main/skills/my-skill
```

Corenexia should:

1. Fetch repository metadata.
2. Require a pinned commit SHA.
3. Locate a `corenexia.skill.json` manifest.
4. Validate the manifest.
5. Inspect files included in the skill.
6. Check dependency declarations.
7. Run tests in the sandbox.
8. Compute file hashes.
9. Assign a trust level.
10. Ask the user to approve install.
11. Store the installed skill in the local registry.
12. Expose it through REST and MCP.

GitHub import must not mean:

> Download arbitrary internet code and run it.

It must mean:

> Import a declared skill, pin it, test it, sandbox it, and track provenance.

### 3. Skill Search Before Code Generation

The orchestrator should not always write new Python first.

The new execution order should be:

1. Understand the user task.
2. Search installed skills.
3. If a matching trusted skill exists, call it.
4. If no matching skill exists, write temporary Python.
5. Run the temporary Python in the sandbox.
6. If it works well, offer to save it as a reusable skill.

This changes Corenexia from:

> The agent writes code every time.

to:

> The agent grows and reuses a trusted skill library.

That is a much stronger product.

### 4. Skill Registry

Corenexia should have a registry of skills.

Start with a local registry in SQLite. Later, support remote/private registries.

The registry should track:

- skill ID.
- name.
- version.
- description.
- source type.
- source URL.
- commit SHA.
- file hash.
- install time.
- last verified time.
- trust level.
- permissions.
- dependency lock.
- test status.
- eval score.
- usage count.
- failure count.
- owner.
- enabled/disabled state.

Trust levels:

- official.
- verified.
- organization-approved.
- community.
- local.
- untrusted.

The UI should make trust obvious.

### 5. Skill Marketplace

Once local skills work, create a marketplace layer.

Marketplace types:

- official Corenexia skills.
- community GitHub skills.
- private company registry.
- team-approved internal skills.

Marketplace features:

- search.
- install.
- update.
- verify.
- disable.
- rollback.
- view permissions.
- view source.
- view test results.
- view usage.
- view security score.

This turns Corenexia into a platform rather than a single app.

### 6. Multi-Provider AI Layer

The current code has an Anthropic provider and a Gemini stub. The long-term product should be model-agnostic.

Add providers for:

- OpenAI.
- Anthropic.
- Gemini.
- OpenRouter-compatible APIs.
- local OpenAI-compatible models.

The provider layer should support:

- tool calling.
- structured output.
- streaming.
- cost tracking.
- retries.
- timeouts.
- model selection.
- fallback models.

The user should be able to choose:

- fastest model.
- cheapest model.
- strongest reasoning model.
- local/private model.
- per-skill model policy.

### 7. Connectors

Corenexia should eventually connect to places where work lives.

Important connectors:

- GitHub.
- GitLab.
- Google Drive.
- Gmail.
- Slack.
- Notion.
- Linear.
- Jira.
- Postgres.
- Snowflake.
- S3.
- local files.
- web pages.

But connectors should be permissioned and auditable.

Connectors and skills are different:

- Connectors fetch or write external data.
- Skills perform reusable work.

Example:

1. GitHub connector fetches repo files.
2. Repo analysis skill scans them.
3. Corenexia records the run.
4. MCP client receives the result.

### 8. Automation Layer

Corenexia should eventually run outside chat.

Triggers:

- webhook received.
- PR opened.
- issue created.
- file uploaded.
- Slack command sent.
- scheduled time.
- MCP client call.
- API call.

Examples:

- Run a repo risk scan on every PR.
- Summarize new contracts uploaded to a folder.
- Validate spreadsheets every morning.
- Run a compliance checklist weekly.
- Generate a changelog when a release branch is created.

This makes Corenexia useful as infrastructure, not only a chat companion.

## New Product Architecture

The future architecture should look like this:

```text
AI Clients
  ChatGPT / Claude / Codex / custom agents / apps
        |
        v
MCP + REST Gateway
        |
        v
Orchestrator
  - classify task
  - search skills
  - select skill
  - request approval if needed
  - execute skill or generated code
  - summarize result
        |
        v
Skill Runtime
  - installed skills
  - GitHub-imported skills
  - generated skills
  - MCP-wrapped tools
        |
        v
Sandbox Layer
  - Docker
  - gVisor
  - future E2B/microVM
        |
        v
Audit + Observability
  - run logs
  - code executed
  - skill provenance
  - cost
  - tokens
  - traces
  - approvals
```

## Required Feature Set

### Core Runtime

- General-purpose system prompt.
- Skill search before code generation.
- Installed skill registry.
- Skill execution tool.
- Generated code execution tool.
- Run persistence.
- Full audit logs.
- Output schemas.
- Error handling.
- retry/repair loop.

### MCP Surface

Expose more than one broad `orchestrate` tool.

Recommended MCP tools:

- `orchestrate`.
- `list_skills`.
- `search_skills`.
- `get_skill`.
- `run_skill`.
- `install_skill_from_github`.
- `list_templates`.
- `run_template`.
- `get_run_status`.
- `get_run_result`.
- `create_skill_from_run`.

Models choose tools better when tool names are specific. A single broad tool is good for the MVP, but a larger product needs a richer tool surface.

### REST API

Recommended endpoints:

- `GET /v1/skills`
- `GET /v1/skills/{skill_id}`
- `POST /v1/skills/import/github`
- `POST /v1/skills/{skill_id}/run`
- `POST /v1/skills/{skill_id}/verify`
- `POST /v1/skills/{skill_id}/enable`
- `POST /v1/skills/{skill_id}/disable`
- `DELETE /v1/skills/{skill_id}`
- `POST /v1/runs/{run_id}/promote-to-skill`
- `GET /v1/registry/search`

### Frontend

Add a skill management section to God View:

- installed skills.
- import from GitHub.
- skill details.
- permissions.
- source/provenance.
- test results.
- execution history.
- enable/disable.
- upgrade/rollback.
- create skill from run.

Add runtime views:

- run timeline.
- skill selection reasoning.
- generated code preview.
- sandbox output.
- cost and tokens.
- approvals.
- risk warnings.

## Security Strategy

Security is the product. If Corenexia runs arbitrary skills from GitHub, trust and isolation become the main value.

Rules:

1. Never run imported code directly on the host.
2. Never install unpinned GitHub code.
3. Never allow network by default.
4. Never pass secrets into sandbox unless explicitly approved.
5. Never allow host filesystem write access by default.
6. Always track source URL, commit SHA, file hashes, and dependency lock.
7. Always display permissions before install.
8. Always run tests before enabling an imported skill.
9. Always keep an audit trail of code executed.
10. Always support disabling or revoking a skill.

Skill permissions should be explicit:

```json
{
  "network": false,
  "filesystem": "readonly",
  "allowed_hosts": [],
  "secrets": [],
  "max_runtime_seconds": 30,
  "max_memory": "512m"
}
```

High-risk actions should require approval:

- network access.
- secret access.
- writing files.
- calling external APIs.
- installing dependencies.
- importing GitHub skills.
- updating skills.
- using unverified skills.

## GitHub Skill Import Design

### Import Flow

```text
User submits GitHub URL
        |
        v
Fetch metadata
        |
        v
Resolve commit SHA
        |
        v
Download archive
        |
        v
Find manifest
        |
        v
Validate manifest
        |
        v
Static scan
        |
        v
Sandbox test
        |
        v
Risk summary
        |
        v
User approval
        |
        v
Install in registry
```

### Manifest Requirements

Each GitHub skill should include:

- `corenexia.skill.json`.
- entrypoint file.
- examples.
- tests.
- dependency declaration.
- permission declaration.
- README or description.

Optional:

- eval cases.
- output schema.
- icon.
- tags.
- supported models.
- minimum Corenexia version.

### Static Scan

Static checks should flag:

- network calls.
- subprocess usage.
- filesystem writes.
- dangerous imports.
- environment variable access.
- secrets handling.
- shell command execution.
- dependency install commands.
- obfuscated code.

Static scan should not be treated as perfect security. It is an early warning layer before sandbox testing.

### Sandbox Test

Each skill should run in the same hardened sandbox used for generated Python.

Test outputs:

- passed/failed.
- stdout.
- stderr.
- duration.
- exit code.
- memory behavior if available.
- network blocked result.

### Skill Storage

Store:

- unpacked skill files in a controlled directory.
- metadata in SQLite initially.
- file hashes for tamper detection.
- original source URL.
- commit SHA.
- installed version.

Later, move to Postgres and object storage for multi-user/cloud deployments.

## Generated Code To Skill Pipeline

This can become a signature feature.

When the orchestrator writes Python and the run succeeds, Corenexia should ask:

> Save this successful solution as a reusable skill?

If approved, Corenexia generates:

- skill manifest.
- cleaned entrypoint.
- input schema.
- output schema.
- test fixture.
- README.
- eval case.

Then it runs the generated skill in the sandbox and installs it only if it passes.

This creates a flywheel:

1. User asks for new capability.
2. Corenexia generates code.
3. Code works.
4. User saves it as a skill.
5. Future runs use the skill instead of regenerating code.
6. The system becomes more reliable over time.

## Template Expansion

Legal and finance should become starter packs, not product boundaries.

Add these packs:

### Software

- repo risk scan.
- dependency audit summary.
- changelog generation.
- test failure summarizer.
- code metrics.
- API surface extraction.

### Data

- CSV summary.
- spreadsheet validation.
- schema inference.
- outlier detection.
- chart-ready aggregation.

### Documents

- PDF extraction.
- DOCX extraction.
- table extraction.
- document comparison.
- citation extraction.

### DevOps

- Dockerfile review.
- Kubernetes manifest linting.
- log summarization.
- incident timeline.

### Business Operations

- meeting note extraction.
- vendor comparison.
- CRM enrichment.
- KPI summary.

### Research

- paper summary.
- bibliography extraction.
- claim/evidence table.
- dataset profiling.

### Security

- secret scan.
- dependency risk summary.
- insecure config detection.
- permission review.

## Current Roadmap First

Before building the bigger runtime, finish the current roadmap. The current roadmap gives the platform credibility.

Important current-roadmap work:

- complete live end-to-end verification with real API keys.
- fix stale roadmap status sections.
- finalize MCP auth.
- verify Docker Compose fully.
- publish docs.
- run frontend build.
- run backend tests.
- verify sandbox behavior.
- verify MCP connection from real clients.
- finish registry publishing only when ready.

Do not start the broad skill marketplace until the current execution path is solid.

The order should be:

```text
Current roadmap
  -> production-grade MCP
  -> skill manifest
  -> local skill registry
  -> GitHub import
  -> skill search/routing
  -> generated code to skill
  -> marketplace
  -> automations
```

## Implementation Phases After Current Roadmap

### Phase 1: Generalize The Product

Goal: remove narrow legal/finance assumptions.

Work:

- update system prompt to general-purpose skill orchestrator.
- keep legal/finance as starter packs.
- add broader template packs.
- update README positioning.
- update frontend text.
- update docs.
- update eval dataset to include software/data/document tasks.

Important prompt change:

Current idea:

```text
Stay strictly within legal and general-finance topics.
```

Future idea:

```text
You are Corenexia, a general-purpose skill orchestrator. Prefer trusted installed skills. If no suitable skill exists, write safe, self-contained Python and run it in the sandbox. Ask for approval before using external networked tools, importing new skills, or handling sensitive secrets.
```

### Phase 2: MCP Production Readiness

Goal: make Corenexia easy for ChatGPT, Claude, and agents to use.

Work:

- mount OAuth routes.
- add missing dependencies.
- implement MCP protected resource metadata.
- implement authorization server metadata.
- add scoped tokens.
- ensure correct `WWW-Authenticate` headers.
- test with MCP Inspector.
- test with OpenAI Responses API remote MCP.
- test with Claude MCP connector.
- improve MCP tool descriptions.
- add narrower MCP tools.

### Phase 3: Skill Manifest And Local Registry

Goal: make skills a first-class runtime object.

Work:

- create `Skill` model.
- create `SkillRegistry`.
- create manifest parser.
- create skill validation.
- create local skill install.
- create `run_skill`.
- add tests.
- add UI list/detail pages.

### Phase 4: GitHub Skill Import

Goal: pull skills from GitHub safely.

Work:

- implement GitHub URL parser.
- resolve branch/tag to commit SHA.
- download archive.
- find manifest.
- validate manifest.
- static scan files.
- run skill tests in sandbox.
- show risk summary.
- require approval.
- install into registry.
- expose through MCP and REST.

### Phase 5: Skill Routing

Goal: use installed skills before generating code.

Work:

- create skill search index.
- add keyword/tag/domain search.
- later add embedding search.
- update orchestrator graph.
- add new `search_skills` node.
- add new `run_skill` node.
- log skill selection reasoning.
- expose selected skill in telemetry.

### Phase 6: Generated Code To Skill

Goal: make Corenexia learn reusable workflows.

Work:

- detect successful generated-code runs.
- allow user to promote run to skill.
- generate manifest.
- generate tests.
- verify generated skill.
- install it.
- add UI action.
- add API endpoint.

### Phase 7: Marketplace

Goal: make skills discoverable and shareable.

Work:

- official skill catalog.
- private registry support.
- signed releases.
- install/update/rollback.
- trust badges.
- usage analytics.
- skill eval scores.

### Phase 8: Automation

Goal: run skills without chat.

Work:

- schedules.
- webhooks.
- GitHub PR triggers.
- Slack command triggers.
- upload triggers.
- run policies.
- approval workflows.

## Risks

### Risk 1: Too Generic Too Early

If Corenexia tries to be everything before the core loop is trusted, it may become confusing.

Mitigation:

- finish the current roadmap first.
- keep demos concrete.
- use "starter packs" to show breadth.
- build skill runtime incrementally.

### Risk 2: Running Untrusted GitHub Code

This is the biggest security risk.

Mitigation:

- pinned commits.
- manifest requirement.
- sandbox execution.
- no network by default.
- approval flows.
- static scans.
- tests before install.
- provenance logs.

### Risk 3: MCP Compatibility Drift

MCP and AI host expectations are evolving.

Mitigation:

- keep MCP tests.
- use official SDKs.
- test with multiple clients.
- keep auth metadata current.
- support Streamable HTTP.

### Risk 4: Poor Tool Selection

Models may choose the wrong tool if descriptions are vague.

Mitigation:

- use narrow tools.
- strong tool descriptions.
- `allowed_tools` guidance for clients.
- skill tags.
- skill examples.
- evals for tool selection.

### Risk 5: Marketplace Trust

Users may not trust community skills.

Mitigation:

- official skill packs.
- verified publishers.
- risk scoring.
- visible permissions.
- audit logs.
- organization allowlists.

## What Corenexia Should Become

The final product should feel like this:

1. A user connects ChatGPT, Claude, or another agent to Corenexia through MCP.
2. The agent asks Corenexia what skills are available.
3. Corenexia returns trusted skills with schemas and descriptions.
4. The user asks for work to be done.
5. Corenexia selects the best installed skill.
6. If no skill exists, Corenexia writes safe Python.
7. The code runs in a hardened sandbox.
8. Results are returned with full traceability.
9. The successful run can become a reusable skill.
10. The team can audit everything later.

That is much larger than legal contract analysis.

## Final Strategic Direction

The most important decision:

> Corenexia should be a general AI Skill Runtime, not a vertical legal/finance app.

Legal and finance should remain as:

- starter packs.
- demos.
- eval domains.
- examples of high-value workflows.

But the platform should support:

- software engineering.
- data analysis.
- document processing.
- research.
- DevOps.
- business operations.
- compliance.
- security.
- internal automation.
- any GitHub-imported executable skill.

The big product is:

> A secure, auditable, self-hostable skill execution layer for AI agents.

That is the direction to pursue after the current roadmap is complete.
