---
description: Master-Orchestrator — wählt das nächste release-relevante GitHub Issue, dispatcht einen isolierten Worker, verifiziert den Commit und lässt Opus vor dem Draft-PR reviewen.
allowed-tools: Read, Bash, Grep, Glob, TodoWrite, Agent, AskUserQuestion
---

# /agora-next-task — Issue-Orchestrator

Du bist der Orchestrator, nicht der Implementer. Die aktive Aufgabenquelle sind GitHub Issues. `README.md`, `docs/STATUS.md` und `ROADMAP.md` liefern Produkt-, Ist- und Release-Kontext.

## Globale Regeln

- Bearbeite genau ein Issue pro Lauf.
- Basis ist aktuelles `origin/main`.
- Nie direkt auf `main` arbeiten.
- Der Implementer arbeitet mit `isolation: worktree` und erzeugt genau einen lokalen Commit.
- Der Implementer pusht, mergt und erstellt keinen PR.
- Nur der Lead darf nach einem `APPROVE` des `agora-opus-reviewer` pushen und einen Draft-PR öffnen.
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

Lies anschließend in dieser Reihenfolge:

1. `README.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. offene GitHub Issues
5. passende ADRs, Contracts und Runbooks

Historische Dokumente unter `docs/archive/` sind keine Taskquelle.

## Schritt 2: Issue auswählen

Priorität:

1. P0/P1-Fehler, Security oder Datenintegrität,
2. rote Required- oder E2E-Gates,
3. Inkonsistenzen in Contracts, Migrationen und Single Sources of Truth,
4. Release-Gates der aktuellen Version,
5. Dokumentations- oder Wartungsschuld mit konkretem Release-Bezug.

Nicht auswählen:

- Issues außerhalb der aktuellen Release-Stufe,
- Multi-User, SaaS, Helm, Federation oder Plugin-System vor `1.0.0`,
- React-/Lovable-Rewrite ohne freigegebene Architekturentscheidung,
- Issues ohne prüfbare Akzeptanzkriterien,
- historische Tasks aus archivierten Planungsdateien.

Bei mehreren gleichwertigen Issues gewinnt:

1. niedrigerer Architektur-Layer,
2. kleinerer atomarer Scope,
3. älteres offenes Release-Blocker-Issue.

## Schritt 3: Issue vollständig prüfen

```bash
gh issue view <NR> --comments
```

Prüfe:

- Problem und gewünschtes Ergebnis sind eindeutig,
- Scope und Out-of-Scope sind vorhanden,
- Akzeptanzkriterien sind ausführbar,
- betroffene Contracts, Migrationen und Security-Grenzen sind benannt,
- Abhängigkeiten oder Parent-Issue sind nachvollziehbar.

Fehlen wesentliche Angaben, ergänze zuerst das Issue oder stoppe mit einem konkreten Drift-Bericht. Nicht raten.

## Schritt 4: Atomaren Slice definieren

```markdown
## Issue #<NR> · <Titel>

- Release-Ziel: <0.9.0 | 0.10.0 | 1.0.0>
- Basis: `origin/main`
- Branch-Vorschlag: <typ>/<issue>-<scope>
- Problem: <ein Satz>
- Scope:
  - <exakte Dateien, Symbole und Interfaces>
- Out-of-Scope:
  - <bewusst ausgeschlossene Nachbararbeit>
- Contracts/Migration/Security:
  - <betroffen oder keine>
- Tests zuerst:
  - <exakte Testpfade und erwartetes RED>
- Issue-Test-Befehl:
  - `<exakter, erneut ausführbarer Befehl>`
- Akzeptanz:
  - <exakte Befehle und erwartete Ergebnisse>
- Gate-Scope:
  - <backend | frontend | schemas | vollständig>
- Dokumentation:
  - <STATUS, ROADMAP, CHANGELOG, Folge-Issue oder keine mit Begründung>
- Stop-Bedingungen:
  - Scope-Drift, unklare Spec, rote Tests oder Gate-Fehler
- Implementer: <passender Subagent>
```

Der Slice muss unabhängig prüfbar und rückrollbar sein.

## Schritt 5: Implementer auswählen

| Aufgabe | Implementer | Modell |
|---|---|---|
| Backend-Refactor, Pydantic, Provider, Persistenz | `agora-refactor-worker` | Sonnet high |
| Tests, E2E, FSM, Quoten | `agora-test-worker` | Sonnet medium |
| Vue, Pinia, Zod, Accessibility | `agora-frontend-worker` | Sonnet medium |
| reine Dokumentation und Changelog | `agora-doc-worker` | Haiku low |
| Evidence- und Wording-Audit | `agora-evidence-auditor` | Sonnet read-only |

Architektur, Cross-Layer-Entscheidungen, Security, Auth, Secrets, Datenmigrationen und ambige Specs müssen vor dem Dispatch vom Lead präzisiert werden. Opus implementiert nicht.

## Schritt 6: Implementer dispatchen

Übergib dem Implementer das vollständige Briefing aus Schritt 4.

Der Implementer muss:

- im automatisch isolierten Worktree arbeiten,
- nur den definierten Slice implementieren,
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
- nur Scope-Dateien explizit stagen,
- erst nach erfolgreichem Abschluss aller Prüfungen genau einen lokalen Commit erzeugen,
- Commit-SHA, Diff-Statistik sowie vollständige Issue-Test-, Pflichtprüfungs- und Gate-Ausgaben zurückgeben,
- nicht pushen, mergen oder einen PR erstellen.

## Schritt 7: Ergebnis selbst verifizieren

Vertraue der Worker-Zusammenfassung nicht. Prüfe frisch:

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

Ein nicht-leerer Status blockiert den Ablauf sofort. Tests, Gate und Opus-Review laufen ausschließlich bei sauberem Worktree weiter — nur so ist garantiert, dass exakt der Inhalt von `<COMMIT_SHA>` geprüft und später gepusht wird.

Führe danach den im Briefing festgelegten Issue-Test frisch aus, speichere die vollständige Ausgabe und prüfe den echten Exit-Code über `PIPESTATUS`:

```bash
<ISSUE_TEST_COMMAND> 2>&1 | tee <ISSUE_TEST_LOG>
test_rc=${PIPESTATUS[0]}
test "$test_rc" -eq 0
```

Ein fehlgeschlagener Issue-Test stoppt den Ablauf sofort. `PASS` darf nur bei Exit-Code 0 gemeldet werden, und `<ISSUE_TEST_LOG>` wird in Schritt 8 an den Opus-Reviewer übergeben.

Wähle anschließend abhängig vom Issue-Scope **genau einen** Gate-Pfad und speichere dessen Ausgabe nach demselben Muster:

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
      echo "Unbekannter Gate-Scope: <GATE_SCOPE>" >&2
      exit 2
      ;;
  esac
} 2>&1 | tee <GATE_LOG>
gate_rc=${PIPESTATUS[0]}
test "$gate_rc" -eq 0
```

Der Issue-Test und das ausgewählte Gate müssen jeweils Exit 0 liefern. Beide vollständigen Ausgaben (`<ISSUE_TEST_LOG>` und `<GATE_LOG>`) werden für Schritt 8 aufbewahrt und dort übergeben. Bei einem Fehler stoppen. Kein kosmetisches Grünmachen und keine unbedingte Ausführung aller Scope-Gates.

## Schritt 8: Opus-Review

Starte genau einen `agora-opus-reviewer` und übergib:

- vollständiges Issue und Akzeptanzkriterien,
- Release-Ziel,
- Basis-SHA und Commit-SHA,
- vollständigen Diff,
- frische gezielte Testausgaben,
- frische Gate-Ausgabe,
- betroffene ADRs, Contracts, Security-Grenzen und Evidence-Hartanker.

Der Reviewer ist read-only und antwortet mit `APPROVE` oder `REQUEST_CHANGES`.

Bei `REQUEST_CHANGES`:

1. keinen Push und keinen PR erstellen,
2. Blocker an denselben Implementer mit engem Korrekturbriefing zurückgeben,
3. höchstens einen Korrekturlauf erlauben,
4. Tests und genau das passende Gate erneut frisch ausführen,
5. Opus erneut reviewen lassen.

Bleibt das Urteil negativ, stoppe mit einem konkreten Bericht.

## Schritt 9: Dokumentationssynchronisation abschließen

Der Dokumentationssync findet zwingend **vor** Push und Draft-PR statt. Verbindliche Reihenfolge des gesamten Ablaufs:

1. Worker-Commit prüfen (Schritt 7),
2. frische Issue-Tests ausführen (Schritt 7),
3. passendes Gate ausführen (Schritt 7),
4. Opus-Review (Schritt 8),
5. Dokumentationssync prüfen (dieser Schritt),
6. bei fehlender Dokumentation: Korrekturlauf mit Amend und vollständiger Wiederholung von Schritt 7 und 8,
7. erst danach pushen (Schritt 10),
8. Draft-PR erstellen (Schritt 10).

Prüfe, ob im selben Slice sachlich korrekt abgebildet sind:

- `docs/STATUS.md`, wenn sich der verifizierte Istzustand geändert hat,
- `ROADMAP.md` nur bei Änderung eines Release-Gates oder der strategischen Reihenfolge,
- `CHANGELOG.md` bei ausgeliefertem Nutzer- oder Betriebsverhalten,
- ein Folge-Issue für notwendige, aber im Slice nicht erledigte Arbeit,
- Issue-Verknüpfung im PR-Body mit `Closes #<NR>`.

Dokumentiere für jedes Artefakt `aktualisiert` oder `NICHT BETROFFEN` mit Begründung.

Ist ein erforderliches Dokumentationsartefakt sachlich betroffen, aber nicht im Commit enthalten, darf nicht gepusht werden. Dann gilt:

1. das Issue einmalig an denselben Implementer zurückgeben,
2. den bestehenden Issue-Commit amendieren statt einen zweiten Commit zu erzeugen,
3. den neuen Commit-SHA erfassen,
4. Schritt 7 (Verifikation, frische Tests, Gate) und Schritt 8 (Opus-Review) für diesen neuen SHA vollständig erneut ausführen.

Erst nach erneutem `APPROVE` darf das Issue weiter zu Schritt 10.

Erzeuge notwendige Folge-Issues vor dem Draft-PR und verlinke sie im PR-Body.

## Schritt 10: Push und Draft-PR

Nur bei `APPROVE` und abgeschlossenem Dokumentationssync:

```bash
git push -u origin <branch>
```

Öffne einen Draft-PR gegen `main` mit:

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

## Abschlussausgabe

```markdown
## Issue-Ergebnis

- Issue: #<NR>
- Worker: <Agent>
- Commit: `<SHA>`
- Issue-Test: PASS
- Pflichtprüfungen: PASS
- Gate: PASS
- Opus: APPROVE
- Draft-PR: <URL>
- Dokumentationssync: <Nachweis>
- Verbleibende Risiken: keine
```
