# Agora — Onboarding für Claude Code

Diese Datei bleibt fachlich synchron zu [AGENTS.md](AGENTS.md). Ausführliche Runbooks liegen unter [docs/runbooks/](docs/runbooks/).

## Projekt

Agora ist ein lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.

Pipeline: Dokument hochladen -> Wissensgraph extrahieren -> Personas spawnen -> OASIS/CAMEL-Simulation ausführen -> belegbaren DACH-Report erzeugen -> Runs/Graphen vergleichen.

Stack: Flask + Pydantic v2 + Vue 3 + Vite + Pinia + Zod + Neo4j 5.18+ + Redis + Ollama/OpenAI-kompatible Endpunkte + OASIS/CAMEL.

## Wichtige Einstiege

- [README.md](README.md) — Projektüberblick und Quickstart
- [docs/status.md](docs/status.md) — Versionen, Tests, Coverage, Milestone-Status
- [PLAN.md](PLAN.md) — operativer Findings- und Maßnahmenplan
- [docs/architecture.md](docs/architecture.md) — Systemarchitektur
- [docs/development.md](docs/development.md) — Entwicklung, Tests, Schema-Drift
- [docs/security.md](docs/security.md) — Security-Hardening
- [docs/runbooks/agent-workflows.md](docs/runbooks/agent-workflows.md) — Agenten- und Worktree-Workflow
- [docs/runbooks/code-review.md](docs/runbooks/code-review.md) — Review- und PR-Regeln

## Harte Regeln

- Nie direkt auf `main` arbeiten oder pushen.
- Feature-/Fix-Branches verwenden: `feat/<scope>-<slug>`, `fix/<scope>-<slug>`, `chore/<scope>-<slug>`.
- Slice-Arbeit in separatem Worktree unter `/private/tmp/agora-<slice-id>/`.
- Keine funktionalen Änderungen ohne passende Tests oder begründeten Smoke-Check.
- Tests sind die Spec; Pflichttests vor Refactors lesen.
- Keine Secrets in Logs, Code, Diffs, Issues, PRs oder Commit-Messages.
- Linux-Pakete mit `nala` statt `apt`; Python-Dependencies über `uv`.
- Keine neuen Query-Tokens (`?token=`); URL-bound Auth läuft über signed Tickets (`?ticket=`).
- Keine Dataclasses für API-Verträge; API-Verträge über Pydantic v2 mit `extra="forbid"`.
- Keine inline kopierten JSON-Schemas; Schemas aus Pydantic ableiten und dumpen.
- Keine hartkodierten UI-Strings in `Step*.vue`; `vue-i18n` Keys verwenden.
- Keine neuen CVE-Ignores ohne Issue, Owner, Deadline und Hardstop.

## Tool-Preflight

Vor Code- oder Architekturänderungen:

1. `code-review-graph::get_minimal_context_tool` für minimalen Kontext und Risikoeinschätzung.
2. Live-Doku-Tooling bei Libraries/Frameworks/SDKs/CLIs.
3. `sequential-thinking` bei Multi-File-Refactors, pipeline-übergreifendem Debugging oder unklarer Spec.
4. Erst danach `rg`, Datei-Reads und Shell.

Fallback auf Standardtools ist okay für Markdown, Bash, YAML, Configs und generierte Artefakte.

## Commands

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

## PR-Workflow

Nach jedem `gh pr create`:

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews  --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

HIGH-Findings vor Merge adressieren, MEDIUM bewusst entscheiden, LOW nur mit Begründung out of scope lassen.

## Verweise

- Agenten-Workflow, Worktrees und Subagent-Gates: [docs/runbooks/agent-workflows.md](docs/runbooks/agent-workflows.md)
- Code-Review-Regeln: [docs/runbooks/code-review.md](docs/runbooks/code-review.md)
- Subagent-Heuristiken: [docs/runbooks/plan.heuristic.md](docs/runbooks/plan.heuristic.md)
- Wording-Glossar: [docs/glossary-wording.md](docs/glossary-wording.md)
- Auth-ADR: [docs/adr/0001-auth-model.md](docs/adr/0001-auth-model.md)
- Evidence-ADR: [docs/adr/0002-evidence-gating.md](docs/adr/0002-evidence-gating.md)
