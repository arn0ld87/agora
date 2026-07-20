# Subagent-Routing

**Stand:** 20.07.2026

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
| Architekturentscheidung | Lead | Lead-Modell mit M3-Reviewer |
| Ambige Spezifikation | Lead | Lead-Modell |
| Security, Auth, Secrets oder Datenmigration | Lead plant, Worker implementiert eng | M3-Reviewer |
| Abschlussreview eines Issue-Commits | `agora-reviewer-m3` | MiniMax-M3, read-only |
| Backend-Refactor | `agora-refactor-worker-m3` | MiniMax-M3 |
| Pydantic-/Schema-Arbeit | `agora-refactor-worker-m3` | MiniMax-M3 |
| Tests, FSM und E2E | `agora-test-worker-m3` | MiniMax-M3 |
| Vue, Pinia, Zod, A11y | `agora-frontend-worker-m3` | MiniMax-M3 |
| Evidence-/Wording-Audit | `agora-evidence-auditor-m3` | MiniMax-M3, read-only |
| Dokumentation | `agora-doc-worker-m3` | MiniMax-M3 |

> **Modell-Migration 20.07.2026:** Die historischen Subagenten ohne `-m3`-Suffix bleiben im Repo, werden aber operativ nicht mehr verwendet. Sie existieren nur noch als Referenz für alte Commits. Das Lead-Modell dieser Session ist MiniMax-M3; alle Subagenten werden über die `-m3`-Variante dispatcht. Der Reviewer-Subagent wurde zusätzlich von `agora-opus-reviewer-m3` auf `agora-reviewer-m3` umbenannt, weil das Modell nicht mehr Opus ist.

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
- einen exakt erneut ausführbaren Issue-Test-Befehl,
- Migration und Rollback, falls Daten betroffen sind,
- exakte Verifikationsbefehle,
- genau einen Gate-Scope: `backend`, `frontend`, `schemas` oder `vollständig`,
- zuständige Dokumentationsquelle,
- Stop-Bedingungen.

### 3. Isolierten Worker dispatchen

Schreibende Worker besitzen `isolation: worktree`. Der Lead übergibt das vollständige Briefing; der Worker sieht den bisherigen Chat nicht und erhält nur den für das Issue erforderlichen Kontext.

Der Worker:

1. bearbeitet genau ein Issue,
2. schreibt oder ändert Tests zuerst,
3. implementiert nur den definierten Slice,
4. führt den gezielten Issue-Test bis GREEN aus,
5. führt vor dem lokalen Commit **ausschließlich** die Pflichtprüfungen des im Briefing benannten Gate-Scopes aus, exakt in dieser Reihenfolge:

   | Gate-Scope | Pflichtprüfungen | Gate (genau einer) |
   |---|---|---|
   | `backend` | gezielte Backend-Tests (`uv run pytest <PFADE> -x -q`) → Contract-Tests → Schema-Check → Ruff → mypy | `pre-push-gate.sh backend` |
   | `frontend` | gezielte Frontend-Tests (`bun run test <PFADE>`) → `bun run check` | `pre-push-gate.sh frontend` |
   | `schemas` | Contract-Tests → Schema-Check | `pre-push-gate.sh schemas` |
   | `vollständig` | gezielte Tests aller betroffenen Layer, danach Backend- und Frontend-Prüfungen | `pre-push-gate.sh` |

   FSM- und E2E-Aufgaben sind ein Aufgabentyp, kein eigener Gate-Scope: Der Lead bildet sie im Briefing auf `backend`, `frontend` oder `vollständig` ab; die dort benannten FSM-/E2E-Tests laufen zusätzlich zu den Pflichtprüfungen dieses Scopes.

   Backend-Pflichtprüfungen im Wortlaut:

   ```bash
   cd backend
   uv run pytest tests/contracts/ -x -q
   uv run python -m app.contracts.dump_schemas --check
   uv run ruff check app/ tests/
   uv run mypy app
   ```

   Für reine Frontend-Aufgaben werden keine Backend-Prüfungen ausgeführt.

6. führt anschließend genau **ein** dazu passendes Scope-Gate aus,
7. synchronisiert sachlich betroffene Dokumentationsartefakte im selben Slice,
8. staged nur Scope-Dateien,
9. erzeugt erst nach Exit 0 aller Prüfungen genau einen lokalen Commit,
10. liefert Commit-SHA, Diff-Statistik sowie vollständige Issue-Test-, Pflichtprüfungs- und Gate-Ausgaben zurück,
11. pusht, mergt und erstellt keinen PR.

Ein fehlender Prüfbefehl, ein unklarer Exit-Code oder ein Fehler blockiert den Commit. Ruff-Autofixes dürfen niemals pauschal mit `uv run ruff check --fix .` über das Repository laufen.

### 4. Lead-Verifikation

Der Lead prüft frisch:

```bash
git show --stat --oneline <COMMIT_SHA>
git diff --check <BASE_SHA>...<COMMIT_SHA>
git diff --name-only <BASE_SHA>...<COMMIT_SHA>

worktree_status="$(git status --short)"

if [ -n "$worktree_status" ]; then
  printf '%s\n' "$worktree_status"
  echo "Worktree enthält uncommittete Änderungen." >&2
  exit 1
fi
```

Ein nicht-leerer Worktree blockiert den Ablauf sofort. Tests, Gate und Opus-Review laufen nur bei sauberem Worktree, damit exakt der Inhalt von `<COMMIT_SHA>` geprüft und später gepusht wird.

Danach läuft der im Briefing festgelegte Issue-Test erneut, mit `tee` gesichert und über `PIPESTATUS` geprüft:

```bash
<ISSUE_TEST_COMMAND> 2>&1 | tee <ISSUE_TEST_LOG>
pipeline_rcs=("${PIPESTATUS[@]}")
test "${pipeline_rcs[0]}" -eq 0
test "${pipeline_rcs[1]}" -eq 0
```

Anschließend wird abhängig vom Scope genau ein Gate ausgeführt und ebenso gesichert:

```bash
{
case "<GATE_SCOPE>" in
  backend)
    bash scripts/pre-push-gate.sh backend
    ;;
  frontend)
    bash scripts/pre-push-gate.sh frontend
    ;;
  schemas)
    bash scripts/pre-push-gate.sh schemas
    ;;
  vollständig)
    bash scripts/pre-push-gate.sh
    ;;
  *)
    exit 2
    ;;
esac
} 2>&1 | tee <GATE_LOG>
gate_rcs=("${PIPESTATUS[@]}")
test "${gate_rcs[0]}" -eq 0
test "${gate_rcs[1]}" -eq 0
```

Issue-Test, Gate und das Schreiben beider Protokolle müssen Exit 0 liefern. Der Lead übergibt ihre vollständigen, frisch erzeugten Ausgaben an den Reviewer. Bei Fehlern stoppen; kein automatischer Endlos-Fix-Loop und keine unbedingte Ausführung aller Scope-Gates.

Bei zwei parallelen Issues werden Test und Gate in den jeweiligen Worktrees ausgeführt. Ein Fehler stoppt nur das betroffene Issue, sofern die nachgewiesene Unabhängigkeit des anderen Issues weiterhin gilt.

### 5. M3-Review

Der Lead startet `agora-reviewer-m3` mit:

- vollständigem Issue und Akzeptanzkriterien,
- Release-Ziel,
- Basis-SHA und Commit-SHA,
- vollständigem Diff,
- frischen Test- und Gate-Ausgaben,
- betroffenen ADRs, Contracts, Security-Grenzen und Evidence-Hartankern.

Der Reviewer antwortet mit `APPROVE` oder `REQUEST_CHANGES`.

Bei `REQUEST_CHANGES` ist höchstens ein enger Korrekturlauf erlaubt. Danach werden Tests, Gate und Review vollständig wiederholt. Ohne `APPROVE` gibt es keinen Push und keinen PR.

### 6. Dokumentationssync

Vor Push und PR wird für jedes Issue nachgewiesen:

- `docs/STATUS.md`: aktualisiert, wenn sich der verifizierte Istzustand geändert hat, sonst `NICHT BETROFFEN` mit Begründung,
- `ROADMAP.md`: aktualisiert bei geändertem Release-Gate oder strategischer Reihenfolge, sonst `NICHT BETROFFEN` mit Begründung,
- `CHANGELOG.md`: aktualisiert bei ausgeliefertem Nutzer- oder Betriebsverhalten, sonst `NICHT BETROFFEN` mit Begründung,
- Folge-Issue: erstellt für notwendige, aber nicht erledigte Folgearbeit, sonst `NICHT BETROFFEN` mit Begründung.

Fehlt ein sachlich erforderliches Datei-Artefakt, wird nicht gepusht. Der bestehende lokale Issue-Commit wird einmalig korrigiert und amendiert; danach laufen Lead-Verifikation und Opus-Review für den neuen SHA vollständig erneut.

### 7. Pull Request

Nur nach `APPROVE` und vollständigem Dokumentationssync pusht der Lead den Issue-Branch und öffnet einen separaten Draft-PR.

Der Pull Request enthält:

- Summary,
- Release-Ziel,
- Scope und Out-of-Scope,
- Issue-Test mit Ergebnis,
- sequenzielle Pflichtprüfungen mit Ergebnis,
- genau das ausgeführte Scope-Gate mit Ergebnis,
- Dokumentationssync und Folge-Issues,
- M3-Review-Ergebnis,
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
- alle Scope-Gates unabhängig vom Issue ausführen,
- mehr als einen automatischen Korrekturlauf starten,
- direkte Änderungen oder Fast-Forward-Pushes auf `main`.
