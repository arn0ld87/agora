# AGENTS.md

Guidance fuer Codex und andere Agent-Runtimes in diesem Repository. Die ausfuehrlichen Workflows liegen unter [docs/runbooks/](docs/runbooks/).

## Projekt

Agora ist ein lokal-first Multi-Agent-Simulator fuer DACH-Zielgruppenreaktionen.

Pipeline: Dokument hochladen -> Wissensgraph extrahieren -> Personas spawnen -> OASIS/CAMEL-Simulation ausfuehren -> belegbaren DACH-Report erzeugen -> Runs/Graphen vergleichen.

Stack: Flask + Pydantic v2 + Vue 3 + Vite + Pinia + Zod + Neo4j 5.18+ + Redis + Ollama/OpenAI-kompatible Endpunkte + OASIS/CAMEL.

Wichtige Einstiege:

- [README.md](README.md) - Projektueberblick und Quickstart
- [docs/status.md](docs/status.md) - Versionen, Tests, Coverage, Milestone-Status
- [PLAN.md](PLAN.md) - operativer Findings- und Massnahmenplan
- [docs/architecture.md](docs/architecture.md) - Systemarchitektur
- [docs/development.md](docs/development.md) - Entwicklung, Tests, Schema-Drift
- [docs/security.md](docs/security.md) - Security-Hardening
- [docs/runbooks/agent-workflows.md](docs/runbooks/agent-workflows.md) - Agenten- und Worktree-Workflow
- [docs/runbooks/code-review.md](docs/runbooks/code-review.md) - Review- und PR-Regeln

## Harte Regeln

- Nie direkt auf `main` arbeiten oder pushen.
- Feature-/Fix-Branches verwenden: `feat/<scope>-<slug>`, `fix/<scope>-<slug>`, `chore/<scope>-<slug>`.
- Slice-Arbeit in separatem Worktree unter `/private/tmp/agora-<slice-id>/`.
- Keine funktionalen Aenderungen ohne passende Tests oder begruendeten Smoke-Check.
- Tests sind die Spec; Pflichttests vor Refactors lesen.
- Keine Secrets in Logs, Code, Diffs, Issues, PRs oder Commit-Messages.
- Keine echten `.env`-Dateien committen; `.env.example` nutzen.
- Linux-Pakete mit `nala` statt `apt`; Python-Dependencies ueber `uv`.
- Keine US-Cloud-Lock-ins einfuehren; Ollama-/OpenAI-kompatible Fallbacks bleiben Pflicht.
- Keine neuen Query-Tokens (`?token=`); URL-bound Auth laeuft ueber signed Tickets (`?ticket=`).
- Keine Dataclasses fuer API-Vertraege; API-Vertraege ueber Pydantic v2 mit `extra="forbid"`.
- Keine inline kopierten JSON-Schemas; Schemas aus Pydantic ableiten und dumpen.
- Keine hartkodierten UI-Strings in `Step*.vue`; `vue-i18n` Keys verwenden.
- Keine hartkodierten CAMEL-/OASIS-Token-Limits; zentrale Resolver verwenden.
- Keine neuen CVE-Ignores ohne Issue, Owner, Deadline und Hardstop.

## Tool-Preflight

Vor Code- oder Architektur-Aenderungen:

1. `code-review-graph::get_minimal_context_tool` fuer minimalen Kontext und Risikoeinschaetzung.
2. Live-Doku-Tooling bei Libraries/Frameworks/SDKs/CLIs, z. B. Vue, Pydantic, Flask, Neo4j, OASIS/CAMEL, Ollama, Vite, pytest, `uv`, Docker.
3. `sequential-thinking` bei Multi-File-Refactors, pipeline-uebergreifendem Debugging oder unklarer Spec.
4. Erst danach `rg`, Datei-Reads und Shell.

Fallback auf Standardtools ist okay fuer Markdown, Bash, YAML, Configs und generierte Artefakte.

## Commands

Alle Commands laufen vom Repo-Root.

```bash
npm run setup:all
npm run dev
npm run check
```

Backend:

```bash
cd backend && uv sync --group dev
cd backend && uv run pytest -x -q
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run python -m app.contracts.dump_schemas
cd backend && uv run ruff check . && uv run mypy app
```

Frontend:

```bash
cd frontend && npm ci
cd frontend && npm run check
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npm run build
```

Schema-Drift:

```bash
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

Prod-Stack-Smoke:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
docker exec agora curl -fsS http://localhost:5001/health
```

## PR-Workflow

Nach jedem `gh pr create`:

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews  --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

Gemini-Code-Assist-Findings:

1. HIGH immer vor Merge adressieren.
2. MEDIUM bewusst entscheiden und dokumentieren.
3. LOW kann mit Begruendung out of scope bleiben.

Erst nach Findings-Sichtung mergen:

```bash
git checkout main
git merge --ff-only <branch>
git push origin main
```

## Aktive Epics

- **Design Language v4 - App-Shell-Port** laeuft auf Integration-Branch `feat/design-v4-epic`.
  Spec: [docs/design/2026-05-11-design-v4-app-shell-epic.md](docs/design/2026-05-11-design-v4-app-shell-epic.md).
  JSX-Quellen liegen unter [design/v3-source/](design/v3-source/).
  Neue v4-Komponenten bleiben in `frontend/src/components/v4/{shell,forms,data,steps}/`.
- **v1.0-Output-Vertrag** wird ueber [PLAN.md](PLAN.md) und [docs/status.md](docs/status.md) verfolgt.

## Verweise

- Agenten-Workflow, Worktrees und Subagent-Gates: [docs/runbooks/agent-workflows.md](docs/runbooks/agent-workflows.md)
- Code-Review-Regeln: [docs/runbooks/code-review.md](docs/runbooks/code-review.md)
- Subagent-Heuristiken: [docs/runbooks/plan.heuristic.md](docs/runbooks/plan.heuristic.md)
- Wording-Glossar: [docs/glossary-wording.md](docs/glossary-wording.md)
- Auth-ADR: [docs/adr/0001-auth-model.md](docs/adr/0001-auth-model.md)
- Evidence-ADR: [docs/adr/0002-evidence-gating.md](docs/adr/0002-evidence-gating.md)
