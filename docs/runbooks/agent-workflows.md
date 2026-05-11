# Agenten-Workflows

Dieses Runbook enthält die operativen Regeln für Agentenarbeit im Agora-Repo. Die kurze Pflichtfassung steht in [AGENTS.md](../../AGENTS.md) und [CLAUDE.md](../../CLAUDE.md).

## Preflight

Vor Code- oder Architekturänderungen:

1. `code-review-graph::get_minimal_context_tool` mit einer konkreten Task-Beschreibung.
2. Live-Doku bei Libraries, Frameworks, SDKs oder CLIs.
3. `sequential-thinking` bei Multi-File-Refactors, pipeline-übergreifendem Debugging oder unklaren Specs.
4. Danach erst direkte Datei-Reads, `rg` und Shell.

Für Markdown, Bash, YAML, Configs und generierte Artefakte ist Direkt-Lesen akzeptabel, wenn der Graph keinen Mehrwert liefert.

## Worktree-Strategie

Slice-Arbeit läuft isoliert:

```bash
git worktree add -b feat/<scope-slice-id> /private/tmp/agora-<slice-id> origin/main
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules /private/tmp/agora-<slice-id>/frontend/node_modules
```

Regeln:

- Hauptcheckout nicht mit Slice-Diffs belasten.
- Branch pro Slice.
- Disjunkte Datei-Scopes bei parallelen Slices.
- Keine publizierten Commits rewriten.
- Keine unrelated Änderungen revertieren.

## Subagent-Briefing

Ein Worker-Briefing braucht:

1. Kontext in 3-5 Zeilen.
2. Exakten Worktree-Pfad und Setup-Befehl.
3. Disjunkten Datei-/Verzeichnis-Scope.
4. Konkrete Dateien und erwartete Größenordnung.
5. Relevante Tokens, Stores, i18n-Keys und Contracts.
6. Tests als Pflicht.
7. Doku-Ort für neues Verhalten.
8. Lokale Gates als Abnahmekriterium.
9. Push-/PR-Verbot, wenn der Slice Teil eines Epics ist.
10. Rückgabeformat: Branch, Commit, Test-Delta, Gaps.

## Verification-Gate

Nach Subagent- oder Slice-Arbeit:

```bash
cd frontend
npm run typecheck
npm test -- --run
npm run build
npm run lint
```

Backend-Slice:

```bash
cd backend
uv run pytest -x -q
uv run ruff check .
uv run mypy app
```

Rot heißt: nicht mergen, sondern präzise nacharbeiten.

## Dokumentation

Neue dauerhafte Doku gehört unter `docs/`. Historische Laufzettel gehören nach `docs/archive/worklogs/`.

Status-Counts und Coverage werden nur in [docs/status.md](../status.md) gepflegt. Keine Inline-Testzahlen in README, AGENTS oder CLAUDE.
