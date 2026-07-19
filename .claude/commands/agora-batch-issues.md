---
description: Wählt maximal zwei unabhängige release-relevante GitHub Issues, dispatcht je einen isolierten Worker und lässt jeden Commit von Opus prüfen.
allowed-tools: Read, Bash, Grep, Glob, TodoWrite, Agent, AskUserQuestion
---

# /agora-batch-issues — paralleler Issue-Orchestrator

Du bist der Lead und Orchestrator. Du implementierst nicht selbst. Die aktive Taskquelle sind GitHub Issues; README, STATUS und ROADMAP liefern nur Produkt-, Ist- und Release-Kontext.

## Ziel

Bearbeite maximal zwei voneinander unabhängige Issues parallel. Jedes Issue erhält genau einen Implementer, einen isolierten Worktree, genau einen lokalen Commit, ein eigenes Opus-Review und einen eigenen Draft-PR.

## Globale Regeln

- Basis ist aktuelles `origin/main`.
- Nie direkt auf `main` arbeiten.
- Keine Agent Teams; verwende normale Subagenten.
- Maximal zwei Implementer gleichzeitig.
- Subagenten können keine weiteren Agenten starten. Die gesamte Orchestrierung bleibt beim Lead.
- Worker pushen, mergen und erstellen keine PRs.
- Nur der Lead darf nach `APPROVE` pushen und einen Draft-PR öffnen.
- Kein `--no-verify`, Force-Push oder automatischer Endlos-Fix-Loop.
- Keine neue Planungsdatei anlegen.

## Schritt 1: Repository und Release-Kontext

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
git fetch origin --quiet

echo "=== origin/main ==="
git log origin/main --oneline -10

echo "=== Produktversion ==="
cat VERSION

echo "=== Offene Issues ==="
gh issue list --state open --limit 100 \
  --json number,title,labels,milestone,assignees,updatedAt \
  | jq -r '.[] | "#\(.number)\t\(.title)\tmilestone=\(.milestone.title // "-")"'
```

Lies in dieser Reihenfolge:

1. `README.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. vollständige Kandidaten-Issues einschließlich Kommentare
5. passende ADRs, Contracts und Runbooks

Historische Dokumente unter `docs/archive/` sind keine Taskquelle.

## Schritt 2: Kandidaten priorisieren

Priorität:

1. P0/P1, Security oder Datenintegrität,
2. rote Required- oder E2E-Gates,
3. Contract-, Migrations- oder SSoT-Inkonsistenzen,
4. Release-Gates der aktuellen Version,
5. konkrete Wartungs- oder Dokumentationsschuld mit Release-Bezug.

Nicht auswählen:

- Issues außerhalb der aktuellen Release-Stufe,
- Issues ohne prüfbare Akzeptanzkriterien,
- neue Produktbereiche vor ihrem Roadmap-Zeitpunkt,
- React-/Lovable-Rewrite ohne freigegebene Architekturentscheidung,
- historische Tasks aus archivierten Dokumenten.

## Schritt 3: Unabhängigkeit beweisen

Für jeden Kandidaten vollständig ausführen:

```bash
gh issue view <NR> --comments
```

Ermittle voraussichtlich betroffene Dateien und Symbole mit `rg`, `git log` und vorhandenen Codegraph-Werkzeugen.

Zwei Issues dürfen nur parallel laufen, wenn alle Aussagen zutreffen:

- kein Parent-/Child- oder Blocked-by-Verhältnis,
- keine gleichen oder eng gekoppelten Dateien,
- keine gemeinsam geänderten Contracts oder Schemas,
- keine Migration, auf der das zweite Issue aufbaut,
- keine vermutlich gemeinsame Fehlerursache,
- keine konkurrierenden Änderungen an Provider-Routing, Secrets oder Evidence-Hartankern,
- jedes Issue ist unabhängig testbar und rückrollbar.

Bei Unsicherheit nur ein Issue auswählen. Parallelität ist kein Selbstzweck; kaputte Merge-Konflikte sparen erstaunlicherweise keine Zeit.

Gib vor dem Dispatch eine Matrix aus:

```markdown
| Issue | Release | Dateien/Symbole | Abhängigkeiten | Worker | Parallel sicher |
|---|---|---|---|---|---|
| #123 | 0.9.0 | `backend/...` | keine | `agora-refactor-worker` | ja |
```

## Schritt 4: Atomare Briefings

Erstelle pro Issue ein vollständiges, selbständiges Briefing:

```markdown
## Issue #<NR> · <Titel>

- Release-Ziel: <Version>
- Basis: `origin/main`
- Branch-Vorschlag: `fix/<issue>-<scope>`
- Problem: <ein Satz>
- Scope:
  - <exakte Dateien, Symbole und Interfaces>
- Out-of-Scope:
  - <bewusst ausgeschlossene Nachbararbeit>
- Verträge/Migration/Security:
  - <betroffen oder keine>
- Tests zuerst:
  - <exakte Testpfade und erwartetes RED>
- Akzeptanz:
  - <Befehle und erwartete Ergebnisse>
- Gate:
  - <backend|frontend|schemas|vollständig>
- Dokumentation:
  - <STATUS, ROADMAP, CHANGELOG oder keine mit Begründung>
- Stop-Bedingungen:
  - Scope-Drift, rote Gates, unklare Spec, Dateiüberschneidung
- Implementer: <Agentenname>
```

## Schritt 5: Worker wählen

| Aufgabe | Worker | Modell |
|---|---|---|
| Backend-Refactor, Pydantic, Provider, Persistenz | `agora-refactor-worker` | Sonnet high |
| Tests, FSM, E2E und Regressionen | `agora-test-worker` | Sonnet medium |
| Vue, Pinia, Zod und Accessibility | `agora-frontend-worker` | Sonnet medium |
| reine Dokumentation | `agora-doc-worker` | Haiku low |
| Evidence-/Wording-Audit | `agora-evidence-auditor` | Sonnet read-only |

Security, Auth, Secrets, Datenmigration, Cross-Layer-Architektur und ambige Specs müssen vor dem Dispatch vom Lead präzisiert werden. Opus implementiert nicht.

## Schritt 6: Parallel dispatchen

Starte die ausgewählten Worker in derselben Orchestrierungsrunde, damit sie parallel laufen. Übergib jedem Worker ausschließlich sein eigenes vollständiges Briefing.

Jeder Worker muss:

- im durch `isolation: worktree` bereitgestellten Worktree arbeiten,
- genau ein Issue bearbeiten,
- Tests zuerst schreiben oder anpassen,
- das passende Gate ausführen,
- nur Scope-Dateien stagen,
- genau einen lokalen Commit erzeugen,
- Commit-SHA, Diff-Statistik und vollständige Testergebnisse zurückgeben,
- nicht pushen, mergen oder einen PR erstellen.

## Schritt 7: Worker-Ergebnisse verifizieren

Vertraue keiner Zusammenfassung. Prüfe für jeden Worker selbst:

```bash
git show --stat --oneline <COMMIT_SHA>
git diff --check <BASE_SHA>...<COMMIT_SHA>
git diff --name-only <BASE_SHA>...<COMMIT_SHA>
git status --short
```

Prüfe:

- nur erlaubte Dateien geändert,
- genau ein Issue im Commit,
- keine Secrets oder generierten Fremdartefakte,
- gezielte Tests und passendes Gate mit Exit 0,
- kein Konflikt mit dem anderen Issue-Commit.

Bei einem Fehler stoppt nur das betroffene Issue. Das andere darf weiter geprüft werden, wenn es wirklich unabhängig ist.

## Schritt 8: Opus-Review pro Commit

Starte für jeden verifizierten Commit genau einen `agora-opus-reviewer`. Übergib:

- vollständiges Issue und Akzeptanzkriterien,
- Release-Ziel,
- Basis-SHA und Commit-SHA,
- vollständigen Diff,
- gezielte Testausgaben,
- Gate-Ausgabe,
- betroffene ADRs, Contracts, Security-Grenzen und Evidence-Hartanker.

Der Reviewer ist read-only und antwortet mit `APPROVE` oder `REQUEST_CHANGES`.

Bei `REQUEST_CHANGES`:

1. keinen Push und keinen PR erstellen,
2. Blocker an denselben Implementer mit engem Korrekturbriefing zurückgeben,
3. höchstens einen Korrekturlauf erlauben,
4. Tests und Gate erneut frisch ausführen,
5. Opus erneut reviewen lassen.

Bleibt das Urteil negativ, stoppe das Issue mit einem konkreten Bericht.

## Schritt 9: Push und Draft-PR

Nur bei `APPROVE`:

```bash
git push -u origin <branch>
```

Öffne für jedes Issue einen separaten Draft-PR gegen `main`.

PR-Body:

```markdown
## Summary
- <Änderung>

## Release-Ziel
- <Version und Gate>

## Issue
- Closes #<NR>

## Scope
- <geänderte Komponenten>

## Out-of-Scope
- <bewusst ausgelagert>

## Tests
- `<Befehl>` — PASS

## Review
- `agora-opus-reviewer` — APPROVE
```

Keine beiden Issues in einen gemeinsamen PR quetschen. Git kann viel, aber es muss nicht jeden schlechten Gedanken konservieren.

## Schritt 10: Abschlussausgabe

```markdown
## Batch-Ergebnis

| Issue | Worker | Commit | Gate | Opus | Draft-PR |
|---|---|---|---|---|---|
| #123 | agora-refactor-worker | `<sha>` | PASS | APPROVE | <URL> |

### Gestoppt
- keine

### Verbleibende Risiken
- keine
```
