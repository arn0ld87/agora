# Agent-Tooling

Stand: **2026-07-14**

Diese Datei beschreibt die verbindliche Nutzung der Agentenwerkzeuge. Exakte lokale
Versions- und Graphzahlen sind Momentaufnahmen und werden nur eingetragen, wenn sie im
selben Slice erneut verifiziert wurden. Alte Zahlen dekorativ weiterzutragen wäre zwar
traditionelle Dokumentationspflege, aber nicht besonders nützlich.

## Verbindliche Pipeline

Für Architektur-, Delta- und Codebase-Analysen gilt grundsätzlich:

1. **`code-review-graph`** für Struktur, Abhängigkeiten, Flows und betroffene Bereiche
2. **`context7`** für aktuelles Bibliotheks- und Frameworkverhalten
3. **`ctx_batch_execute`** für mehrere große Read-only-Abfragen
4. **`ctx_execute` / `ctx_execute_file`** für gezielte Analyse großer Dateien oder Ausgaben
5. direkte Dateiwerkzeuge nur für fokussierte Bearbeitung und abschließende Verifikation

Die Pipeline ist kein Ersatz für Tests oder direkte Codeprüfung. Sie reduziert nur die
übliche menschliche Methode, erst alles zu lesen und danach festzustellen, dass die
entscheidende Datei woanders lag.

## Werkzeuge

| Tool | Zweck | Installations-/Betriebsmodell | Status |
|---|---|---|---|
| context-mode | Execution-Layer, FTS, große Read-only-Ausgaben, Session-Kontext | Codex-Plugin/MCP mit lokalen Hooks | aktiv; Doctor-Hinweise lokal prüfen |
| code-review-graph | Repository-Graph, Flows, Communities und Delta-Analyse | MCP oder reproduzierbar gepinntes `uvx` | aktiv; vor Architekturarbeit aktualisieren |
| context7 | Primärquellen für Bibliotheken und Frameworks | MCP | bei externem API-/Frameworkverhalten verwenden |
| Codex CLI | Agent-Runtime und Orchestrierung | lokale Installation | aktiv |
| graphify | zusätzlicher versionierter Knowledge-Graph, falls `graphify-out/` vorhanden | Repo-/Skill-abhängig | gezielt, nicht als Testersatz |

## Rechte und Datenschutz

- globale Codex-, Claude- oder Plugin-Konfiguration wird nicht ins Repository kopiert
- keine Auth-Dateien, Tokens, Browserprofile, SSH-Schlüssel oder Keychain-Inhalte lesen
- generierte Graphdaten außerhalb produktiver Artefakte halten, sofern sie nicht bewusst
  unter `graphify-out/` versioniert werden
- keine zusätzlichen Watcher oder Daemons ohne eigenen Maintenance-Slice aktivieren
- externe Inhalte nur über erlaubte, nachvollziehbare Quellen abrufen
- Secrets niemals in Tool-Ausgaben, Issues, PRs oder Fixtures übernehmen

## code-review-graph

Vor Architektur- und größeren Delta-Reviews:

1. Status prüfen
2. Graph bei Bedarf aktualisieren oder neu bauen
3. gezielte Query/Flow-/Community-Abfrage ausführen
4. Ergebnisse gegen betroffene Quelldateien verifizieren
5. nach strukturellen Änderungen den Graph erneut aktualisieren

Reproduzierbarer CLI-Aufruf, solange keine konfliktfreie globale Installation bestätigt ist:

```bash
uvx --from 'code-review-graph==2.3.6' code-review-graph status
```

Die Version bleibt bewusst gepinnt. Ein Upgrade erfolgt nur mit Release-Note-, Lizenz-
und Security-Prüfung in einem eigenen Maintenance-Slice.

## context-mode

`context-mode` verarbeitet große Read-only-Ausgaben und hält den Session-Kontext klein.
PreToolUse-Hooks können direkte Bash-/Read-Nutzung einschränken. Bei lokaler Prüfung sind
mindestens folgende Punkte zu verifizieren:

- Server und Storage erreichbar
- FTS5 aktiv
- Plugin-Hooks geladen
- globales Hooks-Feature korrekt gesetzt
- Minimalabfrage erfolgreich

Doctor-Warnungen werden nicht als „praktisch grün“ umbenannt. Entweder sie sind erklärt
und dokumentiert oder sie bleiben offen.

## context7

`context7` wird verwendet, wenn eine Änderung von aktuellem Verhalten externer
Bibliotheken, Frameworks oder APIs abhängt. Primärquellen und offizielle Dokumentation
haben Vorrang. Repository-eigene Verträge und Tests bleiben trotzdem maßgeblich.

## graphify

Wenn `graphify-out/graph.json` vorhanden ist:

```bash
graphify query "<Frage>"
graphify path "<A>" "<B>"
graphify explain "<Konzept>"
graphify update .
```

- `query`, `path` und `explain` vor breiten Rohdatei-Lesungen bevorzugen
- `graphify-out/wiki/index.md` für Navigation verwenden, falls vorhanden
- `GRAPH_REPORT.md` nur für breite Architekturreviews lesen
- schmutzige generierte Graphdateien sind allein kein Grund, Graphify zu überspringen

## Upgrade- und Rollback-Regeln

Upgrades erfolgen ausschließlich in einem eigenen Maintenance-Slice:

1. offizielle Release Notes, Lizenz und Sicherheitsmeldungen prüfen
2. vorhandene Konfiguration sichern
3. exakte Version pinnen
4. Doctor, Graph-Build und Minimalabfrage ausführen
5. relevante Repository-Gates starten
6. bei Regressionen auf die vorherige Version zurückrollen
7. dieses Dokument nur mit erneut verifizierten Ergebnissen aktualisieren

## Verifikation vor Abschluss eines Agenten-Slices

- [ ] verwendete Graph-/Context-Abfragen sind nachvollziehbar
- [ ] betroffene Quelldateien wurden direkt geprüft
- [ ] relevante Tests und Pre-Push-Gates sind grün
- [ ] Graph nach strukturellen Änderungen aktualisiert
- [ ] keine globalen Konfigurations- oder Secret-Dateien committed
- [ ] neue Tool-Ausnahmen haben Issue, Owner und Rückbaukriterium

## Einschränkungen

- Graphresultate ersetzen weder Tests noch Code-Review
- lokale Doctor-Ergebnisse können zwischen Rechnern abweichen
- Python-3.14-Warnungen sind kein Tooling-Erfolg und kein Freifahrtschein
- exakte Datei-, Knoten-, Kanten- oder Flow-Zahlen veralten nach jedem relevanten Commit
- Tooling darf keinen Produktcode- oder Architektur-Single-Source-of-Truth duplizieren