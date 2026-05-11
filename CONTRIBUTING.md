# Contributing — Agora

Agora ist ein experimenteller Open-Source-Fork unter AGPL-3.0. Diese Datei erklärt Repo-Struktur, Branch-Hygiene und Qualitäts-Gates.

## Welche Datei wofür?

| Datei / Verzeichnis | Zweck |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Kurz-Onboarding für Claude Code |
| [`AGENTS.md`](AGENTS.md) | Kurz-Onboarding für Codex und andere Agent-Runtimes |
| [`PLAN.md`](PLAN.md) | Operative Task-Quelle für `/agora-next-task` Subagent-Orchestrator; definiert Milestones M9–M13 und Task-Slices |
| [`docs/status.md`](docs/status.md) | **Single Source of Truth** für Test-Counts, Coverage und Versionsstände; aktualisiert via `scripts/sync-status.sh` |
| [`docs/architecture.md`](docs/architecture.md) | Systemüberblick und Pipeline |
| [`docs/development.md`](docs/development.md) | Setup, Tests, Branching und Schema-Drift |
| [`docs/glossary-wording.md`](docs/glossary-wording.md) | Verbindliches DACH-Voice-Glossar v1; untersagt US-Marketing-Phrasen (`prediction`, `rehearsal`, `god's eye view`) |
| [`CHANGELOG.md`](CHANGELOG.md) | SemVer-Releases und `[Unreleased]`-Block; Sub-Slice-Einträge hier landen, bevor PR auf main merget |
| [`docs/adr/`](docs/adr/) | Architektur-Decision-Records (ADRs) |
| [`docs/archive/worklogs/`](docs/archive/worklogs/) | Historische Arbeitsprotokolle |
| [`docs/archive/`](docs/archive/) | Reviews, alte Pläne, Logs und historische Artefakte |

## Branch- und PR-Hygiene

1. **Nie auf `main` direkt pushen.** Branch-Name-Format: `feat/<task-scope>-<kurztitel>` (z.B. `feat/layer-meta-slice-44-doku-sync`).

2. **Nach `gh pr create` warten auf Gemini-Code-Assist Review** (~60–120 s). Workflow:
   ```bash
   sleep 90
   gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
   gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
   ```
   Findings sind nach `priority` markiert (HIGH / MEDIUM / LOW). HIGH immer fixen vor Merge, MEDIUM je nach Scope, LOW oft Out-of-Scope.

3. **Linear FF-Merge auf main:** Nach Findings-Review `git checkout main && git merge --ff-only <branch> && git push origin main`.

## Lokale Quality-Gates

Vor jedem Commit ausführen:

```bash
# Backend
cd backend && uv sync --group dev
cd backend && uv run pytest -x -q
cd backend && uv run ruff check . && uv run mypy app

# Frontend
cd frontend && npm ci
cd frontend && npm run check    # lint + test + build (alles)

# Status aktualisieren + Drift prüfen
bash scripts/sync-status.sh
bash scripts/sync-status.sh --check   # exit 0 erwartet

# Schemas generieren
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/      # darf nicht driften
```

## Sub-Slice = ein Commit

Ein Sub-Slice erfordert:
1. **Ein Commit** mit prägnanter Message: `feat/fix/docs(scope): Beschreibung (Refs #NNN, Sub-Slice X)`
2. **Ein Arbeitsprotokoll** unter `docs/archive/worklogs/<YYYY-MM-DD>-slice-<N>-<slug>-arbeitsprotokoll.md` (Ziel, Befund, Geänderte Dateien, Akzeptanz-Checks, Folgen)
3. **Eintrag im `[Unreleased]`-Block** von [`CHANGELOG.md`](CHANGELOG.md) (Format: `- **Sub-Slice X (...)**: Kurzbeschreibung. Refs #NNN.`)

Commits sind atomar — alle Tests und Akzeptanz-Checks müssen grün sein, bevor der Commit gepusht wird.

## Keine US-Marketing-Phrasen

Agora-Dokumentation und -Prompts nutzen DACH-Voice (Du-Form, sachlich). Explizit verboten:
- `prediction` / `public opinion prediction` / `Agentic-Prediction-Engine`
- `rehearsal of the future` / `future prediction`
- `god's eye view` / `high-fidelity digital world`
- `revolutionary` / `seamless` / `state-of-the-art`

Ersatz-Vokabular: siehe [`docs/glossary-wording.md`](docs/glossary-wording.md).

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
