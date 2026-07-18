# Subagent-Routing

**Stand:** 18.07.2026

## Prinzip

Komplexe Aufgaben werden an spezialisierte Subagenten delegiert. Das Lead-Modell wählt das release-relevante GitHub Issue, definiert den atomaren Scope, verifiziert die Umsetzung und verantwortet Commit und Pull Request.

Task-Quelle ist immer ein GitHub Issue. `README.md`, `docs/STATUS.md` und `ROADMAP.md` liefern Produkt-, Ist- und Release-Kontext. Archivierte Pläne sind keine Taskquelle.

## Routing-Matrix

| Aufgabe | Lead/Subagent | Trigger |
|---|---|---|
| Architekturentscheidung | Lead | ADR, Cross-Layer, neue Systemgrenze |
| Ambige Spezifikation | Lead | Issue unklar, Akzeptanz nicht prüfbar |
| Security oder Datenmigration | Lead | Secrets, Auth, Persistenz, Rollback |
| Kritisches Code-Review | Lead oder Reviewer | Contracts, Evidence, Routing, Migration |
| Backend-Refactor | `agora-refactor-worker` | Services, Provider, Persistenz |
| Pydantic-/Schema-Arbeit | `agora-refactor-worker` | Contract plus Spiegel |
| Tests, FSM und E2E | `agora-test-worker` | Regressionen, Gates, Quoten |
| Vue, Pinia, Zod, A11y | `agora-frontend-worker` | Frontend-Slice |
| Evidence-/Wording-Audit | `agora-evidence-auditor` | Read-only Review |
| Dokumentation | `agora-doc-worker` | README, STATUS, ROADMAP, CHANGELOG |

## Lead-Trigger

Diese Situationen werden nicht blind delegiert:

1. Pydantic-Verträge oder persistierte Daten ändern sich.
2. Mehrere Architektur-Layer sind betroffen.
3. Security, Auth, Secrets oder Provider-Routing sind beteiligt.
4. Evidence-Gating oder Prompt-Semantik ändern sich.
5. Das Issue ist widersprüchlich oder besitzt keine prüfbaren Akzeptanzkriterien.
6. Ein neuer Produktbereich soll vorgezogen werden, obwohl er nicht zur aktuellen Release-Stufe gehört.

## Dispatch-Workflow

### 1. Release und Issue prüfen

- `VERSION` lesen
- `docs/STATUS.md` und `ROADMAP.md` prüfen
- offenes Issue vollständig einschließlich Kommentare lesen
- Scope, Out-of-Scope, Abhängigkeiten und Release-Gate bestätigen

### 2. Atomaren Slice definieren

Das Briefing enthält:

- Issue-Nummer und Release-Ziel
- Problem in einem Satz
- genaue Dateien und Interfaces
- Scope und Out-of-Scope
- zuerst zu schreibende Tests
- Migration und Rollback, falls Daten betroffen sind
- exakte Verifikationsbefehle
- zuständige Dokumentationsquelle
- Stop-Bedingungen

### 3. Worktree verwenden

Jeder Implementer arbeitet in einem isolierten Worktree vom aktuellen `origin/main`. Keine Änderungen im Hauptcheckout und keine direkten Pushes auf `main`.

### 4. Implementieren

Der Subagent implementiert nur den definierten Slice. Er committet und pusht nicht selbst, sofern das Lead-Modell nichts anderes ausdrücklich festlegt.

### 5. Verifizieren

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

### 6. Pull Request

Der Pull Request enthält:

- Summary
- Release-Ziel
- Scope und Out-of-Scope
- Tests mit Ergebnis
- Migration/Rollback, falls relevant
- `Closes #<Issue>` oder `Refs #<Issue>`

## Anti-Patterns

- Aufgaben aus archivierten Plänen auswählen
- Subagenten ohne vollständiges Briefing dispatchen
- mehrere unabhängige Issues in einen Slice mischen
- neue Features außerhalb des aktuellen Release-Gates vorziehen
- Tests oder Reviews aus Kostengründen auslassen
- Subagent-Output ungeprüft committen
