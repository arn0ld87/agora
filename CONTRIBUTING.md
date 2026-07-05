# Contributing — Agora

Agora ist ein experimenteller Open-Source-Fork unter AGPL-3.0. Diese Datei erklärt Repo-Struktur, Branch-Hygiene und Qualitäts-Gates.

## Welche Datei wofür?

| Datei / Verzeichnis | Zweck |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Anleitung für Claude-Code-Agents: PR-Workflow, Layer-Tabelle, Subagent-Routing, Stack-Map, Verboten-Liste |
| [`AGENTS.md`](AGENTS.md) | Anleitung für Codex-Plugin und andere Integrations-Agents |
| [`PLAN.md`](PLAN.md) | Operative Task-Quelle für `/agora-next-task` Subagent-Orchestrator; definiert Milestones M9–M13 und Task-Slices |
| [`docs/STATUS.md`](docs/STATUS.md) | **Single Source of Truth** für Test-Counts (Backend/Frontend) und Versionsstände; auto-generiert via `scripts/sync-status.sh` |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Strategische Now/Next/Later-Sicht; definiert Milestones und längerfristige Architektur-Ziele |
| [`docs/glossary.md`](docs/glossary.md) | Verbindliches DACH-Voice-Glossar v1; untersagt US-Marketing-Phrasen (`prediction`, `rehearsal`, `god's eye view`) |
| [`CHANGELOG.md`](CHANGELOG.md) | SemVer-Releases und `[Unreleased]`-Block; Sub-Slice-Einträge hier landen, bevor PR auf main merget |
| [`docs/decisions/`](docs/decisions/) | Architektur-Decision-Records (ADRs) als `NNNN-<slug>.md` |
| [`docs/runbooks/`](docs/runbooks/) | Detail-Runbooks (Tool-Pflicht, PR-Workflow, Worktree, Subagent-Routing, Architektur) |

## Branch- und PR-Hygiene

1. **Nie auf main direkt pushen.** Branch-Name-Format: `feat/<task-scope>-<kurztitel>` (z.B. `feat/layer-meta-slice-44-doku-sync`). Riskante Backend-Änderungen sollten mit dem Label `needs-python314` markiert werden, um den CI-Check gegen Python 3.14-dev zu triggern.

2. **Nach `gh pr create` warten auf Gemini-Code-Assist Review** (~60–120 s). Workflow:
   ```bash
   sleep 90
   gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
   gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
   ```
   Findings sind nach `priority` markiert (HIGH / MEDIUM / LOW). HIGH immer fixen vor Merge, MEDIUM je nach Scope, LOW oft Out-of-Scope.

3. **Linear FF-Merge auf main:** Nach Findings-Review `git checkout main && git merge --ff-only <branch> && git push origin main`.

## CI-Gates: Pflicht vs. Heavy

### Pflicht-Gates (laufen auf JEDEM Pull Request, kein Label nötig)

| Job | Was | Ziel |
|---|---|---|
| `backend-pr-gate` | `ruff check app/` + `mypy app` + `pytest tests/contracts/ -q` | Lint + Types + Pydantic-Contract-Smoke |
| `frontend-pr-gate` | `bun run lint` + `bun run typecheck` + `bun run build` | ESLint + Vue-TS-Typecheck + Build |

Branch Protection muss `backend-pr-gate` und `frontend-pr-gate` als Required Status Checks konfiguriert haben.

### Heavy-Jobs (nur auf `push:main` oder per Label)

| Job | Trigger | Label |
|---|---|---|
| `backend` | `push:main` oder Label `needs-backend-ci` | Volle Tests + Coverage-Gate |
| `frontend` | `push:main` oder Label `needs-frontend-ci` | Volle Tests + Coverage |
| `security` | `push:main` + workflow_dispatch | pip-audit, bun audit, Gitleaks |

### Lokale Quality-Gates

Vor jedem Commit ausführen:

```bash
# Alle Blöcke laufen vom Repo-Root; Subshells (…) verhindern,
# dass ein cd den Arbeitsordner für die folgenden Blöcke verstellt.

# Backend — Pflicht (entspricht PR-Gate)
(cd backend && uv sync --group dev && uv run ruff check app/ && uv run mypy app && uv run pytest tests/contracts/ -q)

# Backend — Heavy (entspricht main-Job)
(cd backend && uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=60)

# Frontend — Pflicht (entspricht PR-Gate)
(cd frontend && bun install --frozen-lockfile && bun run lint && bun run typecheck && bun run build)

# Frontend — Heavy (entspricht main-Job)
(cd frontend && bun run test:coverage)

# Status aktualisieren + Drift prüfen
bash scripts/sync-status.sh
bash scripts/sync-status.sh --check   # exit 0 erwartet

# Schemas generieren
(cd backend && uv run python -m app.contracts.dump_schemas)
git diff --exit-code schemas/      # darf nicht driften
```

## Sub-Slice = ein Commit

Ein Sub-Slice erfordert:
1. **Ein Commit** mit prägnanter Message: `feat/fix/docs(scope): Beschreibung (Refs #NNN, Sub-Slice X)`
2. **Eintrag im `[Unreleased]`-Block** von [`CHANGELOG.md`](CHANGELOG.md) (Format: `- **Sub-Slice X (...)**: Kurzbeschreibung. Refs #NNN.`)

Commits sind atomar — alle Tests und Akzeptanz-Checks müssen grün sein, bevor der Commit gepusht wird.

## Keine US-Marketing-Phrasen

Agora-Dokumentation und -Prompts nutzen DACH-Voice (Du-Form, sachlich). Explizit verboten:
- `prediction` / `public opinion prediction` / `Agentic-Prediction-Engine`
- `rehearsal of the future` / `future prediction`
- `god's eye view` / `high-fidelity digital world`
- `revolutionary` / `seamless` / `state-of-the-art`

Ersatz-Vokabular: siehe [`docs/glossary.md`](docs/glossary.md).

## Layer-Reihenfolge

Architektur-Änderungen erfolgen **layer-aufwärts**. Layer 1 ohne Layer 0 ist verboten. Layer-Semantik: [`CLAUDE.md` § Architektur-Layer](CLAUDE.md#architektur-layer-status).

```
Layer 0: Pydantic-Contracts (grün)
  ↓
Layer 1–6: Backend/Frontend-Hardening (grün)
  ↓
Layer 7–10: Graph/Persona/Deployment/Security (teilweise–offen)
```

---

**Fragen?** → [`CLAUDE.md`](CLAUDE.md) oder [`PLAN.md`](PLAN.md) durchstöbern, ggf. Issue öffnen.
