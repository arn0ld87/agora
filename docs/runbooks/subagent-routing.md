# Subagent-Routing

**Stand:** 19.07.2026

## Prinzip

Komplexe Aufgaben werden an spezialisierte Subagenten delegiert. Das Lead-Modell wählt das release-relevante GitHub Issue, definiert den atomaren Scope, verifiziert die Umsetzung und verantwortet Push und Pull Request.

Task-Quelle ist immer ein GitHub Issue. `README.md`, `docs/STATUS.md` und `ROADMAP.md` liefern Produkt-, Ist- und Release-Kontext. Archivierte Pläne sind keine Taskquelle.

Schreibende Worker laufen in isolierten Worktrees, bearbeiten genau ein Issue und erzeugen genau einen lokalen Commit. Vor jedem Push prüft ein read-only Opus-Reviewer den Commit gegen Issue, Diff, Tests und Gates.

## Befehle

| Befehl | Zweck |
|---|---|
| `/agora-next-task` | genau ein Issue vollständig bearbeiten und reviewen |
| `/agora-batch-issues` | maximal zwei nachweislich unabhängige Issues parallel bearbeiten |

## Routing-Matrix

| Aufgabe | Lead/Subagent | Modell |
|---|---|---|
| Architekturentscheidung | Lead | Opus oder Sonnet mit Opus-Review |
| Ambige Spezifikation | Lead | Opus oder Sonnet |
| Security, Auth, Secrets oder Datenmigration | Lead plant, Worker implementiert eng | Opus-Review high |
| Abschlussreview eines Issue-Commits | `agora-opus-reviewer` | Opus high, read-only |
| Backend-Refactor | `agora-refactor-worker` | Sonnet high |
| Pydantic-/Schema-Arbeit | `agora-refactor-worker` | Sonnet high |
| Tests, FSM und E2E | `agora-test-worker` | Sonnet medium |
| Vue, Pinia, Zod, A11y | `agora-frontend-worker` | Sonnet medium |
| Evidence-/Wording-Audit | `agora-evidence-auditor` | Sonnet medium, read-only |
| Dokumentation | `agora-doc-worker` | Haiku low |

## Lead-Trigger

Diese Situationen werden nicht blind delegiert:

1. Pydantic-Verträge oder persistierte Daten ändern sich.
2. Mehrere Architektur-Layer sind betroffen.
3. Security, Auth, Secrets oder Provider-Routing sind beteiligt.
4. Evidence-Gating oder Prompt-Semantik ändern sich.
5. Das Issue ist widersprüchlich oder besitzt keine prüfbaren Akzeptanzkriterien.
6. Ein neuer Produktbereich soll vorgezogen werden, obwohl er nicht zur aktuellen Release-Stufe gehört.

Der Lead präzisiert Scope, Tests, Migration, Rollback und Stop-Bedingungen vor dem Dispatch. Opus implementiert nicht.

## Parallelitäts-Gate

Maximal zwei schreibende Worker dürfen gleichzeitig laufen. Zwei Issues sind nur parallel sicher, wenn:

- keine Parent-/Child- oder Blocked-by-Beziehung besteht,
- keine gleichen oder eng gekoppelten Dateien betroffen sind,
- keine gemeinsamen Contracts, Schemas oder Migrationen geändert werden,
- keine gemeinsame Fehlerursache wahrscheinlich ist,
- keine konkurrierenden Änderungen an Secrets, Provider-Routing oder Evidence-Hartankern erfolgen,
- jedes Issue unabhängig testbar und rückrollbar ist.

Bei Unsicherheit wird nur ein Issue ausgeführt.

## Dispatch-Workflow

### 1. Release und Issue prüfen

- `VERSION` lesen,
- `docs/STATUS.md` und `ROADMAP.md` prüfen,
- offenes Issue vollständig einschließlich Kommentare lesen,
- Scope, Out-of-Scope, Abhängigkeiten und Release-Gate bestätigen.

### 2. Atomaren Slice definieren

Das Briefing enthält:

- Issue-Nummer und Release-Ziel,
- Problem in einem Satz,
- genaue Dateien, Symbole und Interfaces,
- Scope und Out-of-Scope,
- zuerst zu schreibende Tests,
- Migration und Rollback, falls Daten betroffen sind,
- exakte Verifikationsbefehle,
- zuständige Dokumentationsquelle,
- Stop-Bedingungen.

### 3. Isolierten Worker dispatchen

Schreibende Worker besitzen `isolation: worktree`. Der Lead übergibt das vollständige Briefing; der Worker sieht den bisherigen Chat nicht und erhält nur den für das Issue erforderlichen Kontext.

Der Worker:

1. bearbeitet genau ein Issue,
2. schreibt oder ändert Tests zuerst,
3. implementiert nur den definierten Slice,
4. führt gezielte Tests und das passende Gate aus,
5. staged nur Scope-Dateien,
6. erzeugt genau einen lokalen Commit,
7. liefert Commit-SHA, Diff-Statistik und Testausgaben zurück,
8. pusht, mergt und erstellt keinen PR.

### 4. Lead-Verifikation

Der Lead prüft frisch:

```bash
git show --stat --oneline <COMMIT_SHA>
git diff --check <BASE_SHA>...<COMMIT_SHA>
git diff --name-only <BASE_SHA>...<COMMIT_SHA>
```

Mindestens das passende Gate ausführen:

```bash
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Cross-Layer:

```bash
bash scripts/pre-push-gate.sh
```

Zusätzlich laufen die gezielten Tests aus dem Issue. Bei Fehlern stoppen; kein automatischer Endlos-Fix-Loop.

### 5. Opus-Review

Der Lead startet `agora-opus-reviewer` mit:

- vollständigem Issue und Akzeptanzkriterien,
- Release-Ziel,
- Basis-SHA und Commit-SHA,
- vollständigem Diff,
- frischen Test- und Gate-Ausgaben,
- betroffenen ADRs, Contracts, Security-Grenzen und Evidence-Hartankern.

Der Reviewer antwortet mit `APPROVE` oder `REQUEST_CHANGES`.

Bei `REQUEST_CHANGES` ist höchstens ein enger Korrekturlauf erlaubt. Danach werden Tests, Gate und Review vollständig wiederholt. Ohne `APPROVE` gibt es keinen Push und keinen PR.

### 6. Pull Request

Nur nach `APPROVE` pusht der Lead den Issue-Branch und öffnet einen separaten Draft-PR.

Der Pull Request enthält:

- Summary,
- Release-Ziel,
- Scope und Out-of-Scope,
- Tests mit Ergebnis,
- Opus-Review-Ergebnis,
- Migration/Rollback, falls relevant,
- `Closes #<Issue>` oder `Refs #<Issue>`.

## Anti-Patterns

- Aufgaben aus archivierten Plänen auswählen,
- Subagenten ohne vollständiges Briefing dispatchen,
- mehrere unabhängige Issues in einen Commit oder PR mischen,
- abhängige Issues parallel bearbeiten,
- Worker ohne Worktree-Isolation schreiben lassen,
- Opus als Implementer verwenden,
- Tests oder Reviews aus Kostengründen auslassen,
- Worker-Output ungeprüft pushen,
- mehr als einen automatischen Korrekturlauf starten,
- direkte Änderungen oder Fast-Forward-Pushes auf `main`.
