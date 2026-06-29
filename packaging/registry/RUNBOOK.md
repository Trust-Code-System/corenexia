# Publish runbook (MCP Registry + Smithery)

Everything is **staged** for `github.com/Trust-Code-System/corenexia`. The canonical manifests live
at the repo root: [`../../server.json`](../../server.json) and [`../../smithery.yaml`](../../smithery.yaml).
Nothing here is live until a maintainer runs the steps below — **publishing is outward-facing and
requires explicit go-ahead.**

## Status

- [x] Local git repo initialized, secrets confirmed un-tracked (`.env`, `*.db` git-ignored)
- [x] `server.json` (MCP Registry) + `smithery.yaml` finalized with owner `Trust-Code-System`
- [x] **Public GitHub repo pushed + made public** → <https://github.com/Trust-Code-System/corenexia>
- [ ] Backend image pushed to GHCR  ← needs a `write:packages` token (your `gh` token lacks it)
- [ ] Published to MCP Registry  ← needs interactive `mcp-publisher login github`
- [ ] Listed on Smithery  ← web UI

## Remaining commands (run these yourself — they need interactive auth)

```bash
# 1. (optional) Push the backend image to GHCR so server.json's OCI package resolves.
gh auth refresh -s write:packages                 # grant packages scope (browser)
echo "$(gh auth token)" | docker login ghcr.io -u Lingz450 --password-stdin
docker build -t ghcr.io/trust-code-system/corenexia-backend:0.1.0 -f docker/backend.Dockerfile .
docker push ghcr.io/trust-code-system/corenexia-backend:0.1.0
# then mark the package public in the org's GHCR package settings

# 2. Publish to the MCP Registry (server.json is valid and at the repo root).
#    Install the publisher from github.com/modelcontextprotocol/registry releases, then:
mcp-publisher login github     # browser device-flow — authorize as a Trust-Code-System owner
mcp-publisher validate         # validates ./server.json
mcp-publisher publish          # publishes io.github.Trust-Code-System/corenexia

# 3. Smithery: https://smithery.ai → Add server → connect Trust-Code-System/corenexia
#    (it reads the root smithery.yaml), confirm the /mcp endpoint, publish.
```

> If `mcp-publisher` rejects the namespace casing, set `name` in `server.json` to the exact GitHub
> login casing it reports. If you don't want to publish a GHCR image yet, you can publish the MCP
> entry without the `packages` block (remove it) and add a hosted `remotes` URL later.

## Step 1 — Push the public repo (gh is authed as Lingz450)

> Confirm `Lingz450` can push to the `Trust-Code-System` org (member with repo-create rights).

```bash
# from repo root
gh repo create Trust-Code-System/corenexia --public --source=. --remote=origin --push
# or, if the repo already exists:
# git remote add origin https://github.com/Trust-Code-System/corenexia.git && git push -u origin main
```

Before pushing, sanity-check no secrets are staged:

```bash
git ls-files | grep -E '(^|/)\.env$|\.db$' && echo "STOP: secret tracked" || echo "clean"
```

## Step 2 — Publish the backend image to GHCR

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u Lingz450 --password-stdin
docker build -t ghcr.io/trust-code-system/corenexia-backend:0.1.0 -f docker/backend.Dockerfile .
docker push ghcr.io/trust-code-system/corenexia-backend:0.1.0
# make the package public in the org's GHCR settings so the registry entry is usable
```

(The OCI identifier in `server.json` is `ghcr.io/trust-code-system/corenexia-backend` — lowercase,
as GHCR requires.)

## Step 3 — Publish to the MCP Registry

```bash
# Install the publisher CLI (see modelcontextprotocol/registry releases), then:
mcp-publisher login github        # opens a browser device-flow; authorize as a Trust-Code-System owner
mcp-publisher validate            # validates ./server.json against the schema
mcp-publisher publish             # publishes io.github.Trust-Code-System/corenexia
```

If the validator rejects the namespace casing, set `name` to the exact GitHub login casing the
registry reports (it must match an account/org you can authenticate as).

## Step 4 — List on Smithery

1. Go to <https://smithery.ai> → **Add server** → connect the `Trust-Code-System/corenexia` repo.
2. Smithery reads the root `smithery.yaml`. Confirm the `/mcp` endpoint and config schema.
3. Publish from the Smithery dashboard.

## Notes

- Keep `version` in `server.json` in sync with release tags.
- A hosted public endpoint can be added later as a `remotes` entry in `server.json` once a
  deployment URL exists (the demo site).
- Treat every step here like any irreversible public action: a registry listing is public and cached.
