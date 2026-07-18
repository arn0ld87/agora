---
description: Master-Orchestrator — wählt das nächste release-relevante GitHub Issue, plant einen atomaren Slice, dispatcht einen passenden Subagenten und verifiziert die Umsetzung.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write, TodoWrite, Agent, AskUserQuestion
---

# /agora-next-task — Issue-Orchestrator

Du bist der Orchestrator, nicht der Implementer. Die aktive Aufgabenquelle sind GitHub Issues. `README.md`, `docs/STATUS.md` und `ROADMAP.md` liefern Produkt-, Ist- und Release-Kontext.

## Quellenreihenfolge

1. `README.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. offene GitHub Issues
5. passende ADRs, Verträge und Runbooks

Historische Dokumente unter `docs/archive/` sind keine Taskquelle.

## Schritt 1: Repository und Release-Kontext prüfen

```bash
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet

echo "=== origin/main ==="
git log origin/main --oneline -10

echo "=== Produktversion ==="
cat VERSION

echo "=== Offene Issues ==="
gh issue list --state open --limit 100 \
  --json number,title,labels,milestone,assignees,updatedAt \
  | jq -r '.[] | "#\(.number)\t\(.title)\tmilestone=\(.milestone.title // \"-\")"'
```

Lies anschließend:

```text
README.md
ROADMAP.md
STATUS.md
```

Bestimme die aktuelle Release-Stufe und wähle nur Issues, die zu ihren Freigabekriterien gehören.

## Schritt 2: Issue auswählen

Priorität:

1. P0/P1-Fehler, Security- oder Datenintegritätsblocker
2. rote Required- oder E2E-Gates
3. Inkonsistenzen in Verträgen, Migrationen und Single Sources of Truth
4. Release-Gates der aktuellen Version
5. Dokumentations- oder Wartungsschuld mit konkretem Release-Bezug

Nicht auswählen:

- Issues außerhalb der aktuellen Release-Stufe
- Multi-User, SaaS, Helm, Federation oder Plugin-System vor `1.0.0`
- React-/Lovable-Rewrite ohne eigene freigegebene Architekturentscheidung
- Issues ohne prüfbare Akzeptanzkriterien
- historische Tasks aus archivierten Planungsdateien

Bei mehreren gleichwertigen Issues gewinnt:

1. niedrigerer Architektur-Layer
2. kleinerer atomarer Scope
3. älteres offenes Release-Blocker-Issue

## Schritt 3: Issue prüfen

Lies das vollständige Issue:

```bash
gh issue view <NR> --comments
```

Prüfe:

- Problem und gewünschtes Ergebnis sind eindeutig.
- Scope und Out-of-Scope sind vorhanden.
- Akzeptanzkriterien sind ausführbar.
- betroffene Verträge, Migrationen und Security-Grenzen sind benannt.
- Abhängigkeiten oder Parent-Issue sind nachvollziehbar.

Fehlen wesentliche Angaben, ergänze zuerst das Issue oder stoppe mit einem konkreten Drift-Bericht. Nicht raten.

## Schritt 4: Atomaren Slice planen

Erstelle inline:

```markdown
## Issue #<NR> · <Titel>

- Release-Ziel: <0.9.0 | 0.10.0 | 1.0.0>
- Branch: <typ>/<kurzer-scope>
- Problem: <ein Satz>
- Scope:
  - <konkrete Datei oder Komponente>
- Out-of-Scope:
  - <bewusst ausgeschlossene Nachbararbeit>
- Verträge/Migrationen:
  - <betroffen oder keine>
- Tests zuerst:
  - <exakte Testpfade und erwartetes RED>
- Akzeptanz:
  - <exakte Befehle und erwartete Ergebnisse>
- Dokumentation:
  - STATUS, ROADMAP, CHANGELOG oder keine Änderung mit Begründung
- Implementer: <passender Subagent>
```

Ein Slice darf nur so groß sein, dass er in einem Pull Request unabhängig geprüft und zurückgerollt werden kann.

## Schritt 5: Subagent auswählen

| Aufgabe | Subagent |
|---|---|
| Backend-Refactor, Pydantic, Provider, Persistenz | `agora-refactor-worker` |
| Tests, E2E, FSM, Quoten | `agora-test-worker` |
| Vue, Pinia, Zod, Accessibility | `agora-frontend-worker` |
| Evidence- und Wording-Audit | `agora-evidence-auditor` |
| Dokumentation und Changelog | `agora-doc-worker` |

Architektur, Cross-Layer-Entscheidungen, Security, Datenmigrationen und ambige Specs bleiben beim Lead-Modell.

## Schritt 6: Isolierten Worktree anlegen

Nutze den `using-git-worktrees`-Skill. Ausgangspunkt ist immer aktuelles `origin/main`.

```bash
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet
WT=/Volumes/T7/Projekte/agora-worktrees/<branch>
git worktree add -b <branch> "$WT" origin/main
```

## Schritt 7: Subagent dispatchen

Der Prompt enthält vollständig:

- absoluten Worktree-Pfad
- Issue-Nummer und Release-Ziel
- Problem, Scope und Out-of-Scope
- exakte Dateien und Interfaces
- zuerst zu schreibende Tests
- Akzeptanzbefehle
- Dokumentationspflicht
- Verbot von Commit, Push, `--no-verify`, Force-Push und Scope-Ausweitung

Der Subagent implementiert nur. Der Lead verifiziert, committet und pusht.

## Schritt 8: Verifizieren

Mindestens das passende zentrale Gate ausführen:

```bash
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Bei Cross-Layer-Änderungen das vollständige Gate:

```bash
bash scripts/pre-push-gate.sh
```

Zusätzlich die im Issue genannten gezielten Tests ausführen. Bei Fehlern stoppen. Kein automatischer Endlos-Fix-Loop.

## Schritt 9: Commit und Pull Request

```bash
git add <konkrete-dateien>
git commit -m "<typ>(<scope>): <beschreibung> (Refs #<NR>)"
git push -u origin <branch>

gh pr create \
  --base main \
  --head <branch> \
  --title "<typ>(<scope>): <beschreibung>" \
  --body "$(cat <<'EOF'
## Summary
- <Änderung>

## Release-Ziel
- <Version und Gate>

## Tests
- <Befehl und Ergebnis>

## Scope
- Closes #<NR>

## Out-of-Scope
- <bewusst ausgelagert>
EOF
)"
```

Direkte Fast-Forward-Pushes auf `main` sind verboten. Der Pull Request wird erst nach grünen Gates und Review gemergt.

## Schritt 10: Quellen synchronisieren

Nach erfolgreicher Umsetzung:

- `docs/STATUS.md`, wenn sich der Istzustand geändert hat
- `ROADMAP.md`, nur wenn sich ein Release-Gate oder die strategische Reihenfolge ändert
- `CHANGELOG.md`, wenn Nutzer- oder Betriebsverhalten ausgeliefert wird
- GitHub Issue schließen oder Folge-Issue anlegen

Keine neue Planungsdatei anlegen. Ein abgeschlossenes Issue und die Git-Historie sind das Arbeitsprotokoll.
