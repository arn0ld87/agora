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
- Issue-Test-Befehl:
  - `<exakter, erneut ausführbarer Befehl>`
- Akzeptanz:
  - <Befehle und erwartete Ergebnisse>
- Gate-Scope:
  - <backend | frontend | schemas | vollständig>
- Dokumentation:
  - <STATUS, ROADMAP, CHANGELOG, Folge-Issue oder keine mit Begründung>
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
- den Issue-Test aus dem Briefing mit GREEN abschließen,
- vor dem lokalen Commit Contract-Tests, Schema-Check, Ruff und mypy exakt in dieser Reihenfolge mit Exit 0 ausführen:

  ```bash
  cd backend
  uv run pytest tests/contracts/ -x -q
  uv run python -m app.contracts.dump_schemas --check
  uv run ruff check app/ tests/
  uv run mypy app
  ```

- anschließend genau das im Briefing benannte Scope-Gate ausführen,
- sachlich betroffene Dokumentationsartefakte im selben Slice aktualisieren,
- nur Scope-Dateien stagen,
- erst nach erfolgreichem Abschluss aller Prüfungen genau einen lokalen Commit erzeugen,
- Commit-SHA, Diff-Statistik sowie vollständige Issue-Test-, Pflichtprüfungs- und Gate-Ausgaben zurückgeben,
- für `docs/STATUS.md`, `ROADMAP.md`, `CHANGELOG.md` und Folge-Issue jeweils `aktualisiert` oder `NICHT BETROFFEN` mit Begründung melden,
- nicht pushen, mergen oder einen PR erstellen.

## Schritt 7: Worker-Ergebnisse verifizieren

Vertraue keiner Zusammenfassung. Prüfe für jedes Issue in dessen eigenem Worktree zunächst den Commit:

```bash
cd <WORKTREE_PATH>
issue_blocked=0

git show --stat --oneline <COMMIT_SHA>
git diff --check <BASE_SHA>...<COMMIT_SHA>
git diff --name-only <BASE_SHA>...<COMMIT_SHA>
worktree_status="$(git status --short)"

if [ -n "$worktree_status" ]; then
  printf '%s\n' "$worktree_status"
  echo "Worktree enthält uncommittete Änderungen." >&2
  issue_blocked=1
fi
```

Ein nicht-leerer Status blockiert **dieses** Issue sofort: Tests, Gate und Opus-Review dürfen dafür nicht mehr laufen, und es wird weder gepusht noch ein PR geöffnet. Nur so ist garantiert, dass exakt der Inhalt von `<COMMIT_SHA>` geprüft und später gepusht wird. Der Blocker-Bericht nennt die ausgegebenen uncommitteten Pfade (uncommitted changes nach dem Worker-Commit).

Da jedes Issue in seinem eigenen Worktree verifiziert wird, beendet der Blocker den Batch nicht. Das andere Issue läuft nur weiter, wenn die in Schritt 3 nachgewiesene Unabhängigkeit weiterhin gilt; andernfalls stoppt auch dieses. Verwende hier kein `exit`, das die gemeinsame Orchestrierungs-Shell beenden würde. Das andere Issue muss danach erneut gemäß Schritt 3 auf Unabhängigkeit geprüft werden, bevor es weiterlaufen darf.

Alle weiteren Verifikationsschritte dieses Issues laufen **nur** bei `issue_blocked -eq 0`. Ist das Flag gesetzt, werden Test, Gate und Opus-Review dieses Issues übersprungen und es geht als gestoppt in die Abschlussausgabe.

Führe danach den issue-spezifischen Test frisch aus und bewahre die vollständige Ausgabe auf:

```bash
cd <WORKTREE_PATH>
if [ "$issue_blocked" -eq 0 ]; then
  <ISSUE_TEST_COMMAND> 2>&1 | tee <ISSUE_TEST_LOG>
  pipeline_rcs=("${PIPESTATUS[@]}")
  test_rc=${pipeline_rcs[0]}
  log_rc=${pipeline_rcs[1]}
  if [ "$test_rc" -ne 0 ] || [ "$log_rc" -ne 0 ]; then
    issue_blocked=1
  fi
fi
```

`tee` wird mitgeprüft: Schlägt das Schreiben des Protokolls fehl, fehlt die für Schritt 8 vorgeschriebene vollständige Ausgabe — das Issue gilt dann als gestoppt, auch wenn der Test selbst grün war.

Führe anschließend abhängig vom Issue-Scope **genau einen** Gate-Pfad frisch aus und bewahre auch diese Ausgabe auf:

```bash
cd <WORKTREE_PATH>
if [ "$issue_blocked" -eq 0 ]; then
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
      echo "Unbekannter Gate-Scope: <GATE_SCOPE>" >&2
      exit 2
      ;;
  esac
} 2>&1 | tee <GATE_LOG>
  gate_rcs=("${PIPESTATUS[@]}")
  gate_rc=${gate_rcs[0]}
  gate_log_rc=${gate_rcs[1]}
  if [ "$gate_rc" -ne 0 ] || [ "$gate_log_rc" -ne 0 ]; then
    issue_blocked=1
  fi
fi
```

`issue_blocked=1` bedeutet: dieses Issue ist gestoppt. Es geht nicht in Schritt 8 (Opus-Review), wird nicht gepusht und bekommt keinen PR. Der Batch selbst läuft weiter; das andere Issue wird nur fortgesetzt, wenn seine in Schritt 3 nachgewiesene Unabhängigkeit weiterhin gilt.

Prüfe außerdem:

- nur erlaubte Dateien geändert,
- genau ein Issue im Commit,
- keine Secrets oder generierten Fremdartefakte,
- Issue-Test und ausgewähltes Gate jeweils Exit 0,
- vollständige Test- und Gate-Ausgaben liegen für Schritt 8 vor,
- kein Konflikt mit dem anderen Issue-Commit.

Bei einem Fehler stoppt ausschließlich das betroffene Issue. Das andere darf nur weiter geprüft werden, wenn die in Schritt 3 nachgewiesene Unabhängigkeit weiterhin gilt. Ein Fehler darf weder das andere Issue automatisch stoppen noch durch dessen Erfolg verdeckt werden.

## Schritt 8: Opus-Review pro Commit

Starte für jeden verifizierten Commit genau einen `agora-opus-reviewer`. Übergib:

- vollständiges Issue und Akzeptanzkriterien,
- Release-Ziel,
- Basis-SHA und Commit-SHA,
- vollständigen Diff,
- die in Schritt 7 frisch erzeugte Issue-Test-Ausgabe,
- die in Schritt 7 frisch erzeugte Gate-Ausgabe,
- betroffene ADRs, Contracts, Security-Grenzen und Evidence-Hartanker.

Der Reviewer ist read-only und antwortet mit `APPROVE` oder `REQUEST_CHANGES`.

Bei `REQUEST_CHANGES`:

1. keinen Push und keinen PR erstellen,
2. Blocker an denselben Implementer mit engem Korrekturbriefing zurückgeben,
3. höchstens einen Korrekturlauf erlauben,
4. Tests und genau das passende Gate erneut frisch ausführen,
5. Opus erneut reviewen lassen.

Bleibt das Urteil negativ, stoppe nur das betroffene Issue mit einem konkreten Bericht.

## Schritt 9: Dokumentationssynchronisation abschließen

Prüfe für jedes erfolgreiche Issue vor Push und PR, ob im selben Slice sachlich korrekt abgebildet sind:

- `docs/STATUS.md` bei geändertem verifiziertem Istzustand,
- `ROADMAP.md` bei geändertem Release-Gate oder strategischer Reihenfolge,
- `CHANGELOG.md` bei ausgeliefertem Nutzer- oder Betriebsverhalten,
- ein Folge-Issue für notwendige, aber nicht erledigte Folgearbeit.

Dokumentiere für jedes Artefakt `aktualisiert` oder `NICHT BETROFFEN` mit Begründung. Ist ein erforderliches Datei-Artefakt im Commit nicht enthalten, darf nicht gepusht werden. Gib das betroffene Issue einmalig an denselben Worker zurück, lasse den bestehenden lokalen Commit amendieren und wiederhole für den neuen Commit-SHA Schritt 7 und Schritt 8 vollständig. Dadurch bleibt es bei genau einem Issue-Commit.

Erzeuge notwendige Folge-Issues vor dem Draft-PR und verlinke sie im PR-Body. Der Dokumentationssync eines Issues darf keine Dateien oder Planungen des anderen Issues übernehmen.

## Schritt 10: Push und Draft-PR

Nur bei `APPROVE` und abgeschlossenem Dokumentationssync:

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
- `<Issue-Test-Befehl>` — PASS
- Contract-Tests → Schema-Check → Ruff → mypy — PASS
- `scripts/pre-push-gate.sh <Scope>` — PASS

## Dokumentationssync
- `docs/STATUS.md`: <aktualisiert | NICHT BETROFFEN + Begründung>
- `ROADMAP.md`: <aktualisiert | NICHT BETROFFEN + Begründung>
- `CHANGELOG.md`: <aktualisiert | NICHT BETROFFEN + Begründung>
- Folge-Issue: <URL | NICHT BETROFFEN + Begründung>

## Review
- `agora-opus-reviewer` — APPROVE
```

Keine beiden Issues in einen gemeinsamen PR quetschen. Git kann viel, aber es muss nicht jeden schlechten Gedanken konservieren.

## Schritt 11: Abschlussausgabe

```markdown
## Batch-Ergebnis

| Issue | Worker | Commit | Issue-Test | Gate | Opus | Doku-Sync | Draft-PR |
|---|---|---|---|---|---|---|---|
| #123 | agora-refactor-worker | `<sha>` | PASS | PASS | APPROVE | vollständig | <URL> |

### Gestoppt
- keine

### Nicht erledigte Folgearbeit
- keine

### Verbleibende Risiken
- keine
```
