# CI Egress Allowlist

This document tracks the expected egress targets for GitHub Action workflows using `step-security/harden-runner` in `block` mode.

## Common Endpoints (Required by almost all workflows)

- `github.com:443`: Checkout and other GitHub interactions.
- `api.github.com:443`: GitHub API calls.
- `objects.githubusercontent.com:443`: Downloading action artifacts/assets.
- `proxy.golang.org:443`: Often needed by Go-based actions (like Scorecard or Actionlint).

## Workflow Specific Endpoints

### CI (`ci.yml`)
- **Python Jobs:**
  - `pypi.org:443`
  - `files.pythonhosted.org:443`
- **Frontend Jobs:**
  - `registry.npmjs.org:443`
- **Security Job:**
  - `api.openai.com:443` (LLM interactions)
  - `generativelanguage.googleapis.com:443` (LLM interactions)
  - `auth.docker.io:443`
  - `registry-1.docker.io:443`

### CodeQL (`codeql.yml`)
- `api.github.com:443`
- `github.com:443`
- `objects.githubusercontent.com:443`
- `uploads.github.com:443`

### CVE Monitor (`cve-monitor.yml`)
- `pypi.org:443`
- `files.pythonhosted.org:443`

### Dependency Review (`dependency-review.yml`)
- `api.github.com:443`

### Actionlint (`actionlint.yml`)
- `api.github.com:443`
- `github.com:443`

### Scorecard (`scorecard.yml`)
- `api.github.com:443`
- `api.securityscorecards.dev:443`
- `github.com:443`
- `oss-fuzz-build-logs.storage.googleapis.com:443`
- `www.bestpractices.dev:443`

### E2E Smokes (`e2e-smokes.yml`)
- `registry.npmjs.org:443`
- `playwright.azureedge.net:443` (Browser downloads)
- `results-receiver.actions.githubusercontent.com:443`, `*.blob.core.windows.net:443` — GHA-Actions-Cache-Service. Schon vor CI-Welle 2026-10-02 in allen 7 Jobs vorhanden (Bun-/Playwright-Chromium-Cache via `actions/cache`); deckt seitdem zusätzlich `cache-from: type=gha` der neuen `.github/actions/e2e-prebuild`-Composite-Action (Docker-Image-Build per `docker/bake-action`) ab — keine neuen Endpunkte nötig.
- Alle übrigen Docker-/Paket-Registry-Endpunkte (siehe Job-YAML) deckten den impliziten `docker compose up --build` in `scripts/e2e-up.sh` bereits vorher ab. Seit CI-Welle 2026-10-02 baut `.github/actions/e2e-prebuild` dieselben zwei Images (`agora`: Stage `prod`, `nginx`: Stage `proxy`) explizit per Bake, bevor Playwright startet — identischer Build, nur vorgezogen; die Allowlist musste dafür nicht wachsen.
- Neuer vorgelagerter Job `changes` (Doku-Only-Erkennung, CI-Welle 2026-10-02) braucht nur die vier Common-Endpoints aus dem Kopf dieser Datei — reiner `actions/checkout`, kein Build.

### Docker Image (`docker-image.yml`)
- `auth.docker.io:443`
- `registry-1.docker.io:443`
- `ghcr.io:443`
- `pkg-containers.githubusercontent.com:443`
- `production.cloudflare.docker.com:443`
- `toolbox-data.anchore.io:443` — syft/sbom-action lädt Tool-Binaries (Issue #633)
- `fulcio.sigstore.dev:443`, `rekor.sigstore.dev:443`, `tuf-repo-cdn.sigstore.dev:443` — nur `publish`: `attest-build-provenance` signiert über Public-Good-Sigstore (#1708)
- `release-assets` (nur `v*`-Tags) hat eine eigene, enge Liste: `api.github.com`, `github.com`, `uploads.github.com` (Release-Asset-Upload), `results-receiver.actions.githubusercontent.com` und `*.blob.core.windows.net` (Artefakt-Download) (#1661)

`prod-proxy-smoke` hat bewusst eine engere Liste ohne Paketquellen (`dl-cdn.alpinelinux.org`, `deb.debian.org`, `registry.npmjs.org`). Deshalb darf dort nichts gebaut werden: Der Job startet beide Images aus `build-only` mit `compose up --no-build`. Ein impliziter Compose-Build hing hinter dieser Liste bis zum Job-Timeout (#1708).

### Contract Gates (`contract-gates.yml`)
- `pypi.org:443`
- `files.pythonhosted.org:443`
- `registry.npmjs.org:443`

## Stability Assessment
- The current list is based on typical tool requirements.
- `audit` data from the last 2 weeks confirms these are the primary stable targets.
- E2E tests are stable as they use `stub` mode for LLMs, avoiding external API calls to providers.
- Docker builds are the most complex due to multiple registry interactions.
