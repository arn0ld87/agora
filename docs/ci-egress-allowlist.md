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

### Docker Image (`docker-image.yml`)
- `auth.docker.io:443`
- `registry-1.docker.io:443`
- `ghcr.io:443`
- `pkg-containers.githubusercontent.com:443`
- `production.cloudflare.docker.com:443`

### Contract Gates (`contract-gates.yml`)
- `pypi.org:443`
- `files.pythonhosted.org:443`
- `registry.npmjs.org:443`

## Stability Assessment
- The current list is based on typical tool requirements.
- `audit` data from the last 2 weeks confirms these are the primary stable targets.
- E2E tests are stable as they use `stub` mode for LLMs, avoiding external API calls to providers.
- Docker builds are the most complex due to multiple registry interactions.
