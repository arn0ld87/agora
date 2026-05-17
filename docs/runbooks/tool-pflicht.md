# Tool-Pflicht: Verbindliche Reihenfolge

Datei: `docs/runbooks/tool-pflicht.md` · Stand: 2026-05-17 · Gilt für: Claude Code, Codex, Gemini, pi

## Pipeline (nicht überspringbar)

```
code-review-graph → context7 → sequential-thinking → context-mode → Read/rg/Bash
```

Jeder Schritt ist ein Gate. Erst wenn das aktuelle Gate sinnvoll abgearbeitet ist, geht es
zum nächsten. Die gesamte Pipeline muss VOR dem ersten Read/rg/Bash durchlaufen sein.

---

## Schritt 1: code-review-graph

**Zweck:** Strukturellen Code-Kontext erfassen, bevor du irgendein File liest.

### Tool-Entscheidungsmatrix

| Deine Frage | Graph-Tool | Nicht |
|---|---|---|
| "Was hat sich geändert?" | `detect_changes` → `get_review_context` | `git diff` + Read |
| "Welche Dateien sind betroffen?" | `get_impact_radius` | manuelles Import-Tracing |
| "Welche Flows sind betroffen?" | `get_affected_flows` | `rg` durch alle Service-Files |
| "Wer ruft X auf?" | `query_graph pattern=callers_of` | `rg "X"` |
| "Was ruft X auf, und wer testet X?" | `query_graph pattern=callees_of,tests_for` | `rg` + `find` |
| "Wo ist Funktion/Klasse X definiert?" | `semantic_search_nodes` | `rg "def X"` |
| "Wie ist das Projekt strukturiert?" | `get_architecture_overview` + `list_communities` | mehrere `Read` |
| "Welche Files sind > 300 LOC?" | `find_large_functions_tool` | `wc -l` manuell |
| "Welche Module haben viele Dependents?" | `get_hub_nodes_tool` | `rg` |
| "Wie plane ich einen Refactor?" | `refactor_tool` | manuelle Cross-Repo-Suche |
| "Minimaler Kontext für Aufgabe X?" | `get_minimal_context_tool` | Read ganzer Files |

### Fallback-Regel

Nur wenn der Graph die Frage strukturell nicht beantworten KANN, fällst du auf Read/rg
zurück. Das betrifft typischerweise:

- Bash-Skripte, CI-YAML, Markdown, Config-Files, `.env`, `.json`-Configs
- Generierte Schema-Files (`schemas/`)
- README, CHANGELOG, LICENSE

Bei Unsicherheit: Graph fragen, dann fallback dokumentieren.

---

## Schritt 2: context7

**Zweck:** Aktuelle Library/Framework/SDK-Dokumentation abrufen, bevor du Code schreibst.

### Wann Pflicht

Immer wenn die Aufgabe eines dieser Themen berührt:

- **Backend:** Flask, Pydantic v2, Neo4j Python Driver, Ollama API, CAMEL-AI/OASIS,
  OpenAI-kompatible Chat/Tool-Call-APIs, pytest, uv
- **Frontend:** Vue 3, Vite, Pinia, Vitest, Zod, vue-i18n, Playwright
- **Infra:** Docker, nginx, GitHub Actions, gunicorn

### Workflow

1. `resolve-library-id` → Library-Identifier finden
2. `query-docs` → relevante Code-Snippets/API-Referenzen abrufen
3. Erst danach Code schreiben

### Anti-Pattern

- "Ich kenn die API auswendig" → APIs ändern sich. Context7 zeigt die AKTUELLE Version.
- "Ich google kurz" → Context7 ist schneller und token-effizienter.

---

## Schritt 3: sequential-thinking

**Zweck:** Strukturiertes Durchdenken komplexer Aufgaben, bevor du implementierst.

### Wann Pflicht

- Multi-File-Refactors (2+ Dateien betroffen)
- Pipeline-übergreifende Änderungen (graph → env → simulation → report)
- Debugging über die Flask↔OASIS-Subprozess-Grenze
- Aufgaben mit unklarem Lösungspfad oder ambigen Specs
- Architektur-Entscheidungen (ADR-würdige Änderungen)

### Nicht nötig bei

- Einzel-File-Bugfix mit klarem Root Cause
- Typos, Formatting, Imports sortieren
- README/CHANGELOG-Updates

---

## Schritt 4: context-mode

**Zweck:** Token-Verbrauch minimieren, Output-Management.

### Harte Regel

**ALLER Command-Output > 20 Zeilen MUSS durch `ctx_batch_execute` oder `ctx_execute`.**

Ausnahmen: `Edit`, `Write`, `mkdir`, `rm`, `mv`, `git add/commit/push`.

### Tool-Wahl

| Szenario | Tool |
|---|---|
| Mehrere Commands + mehrere Suchfragen | `ctx_batch_execute(commands, queries)` — EIN Call |
| Ein Command, große Ausgabe | `ctx_execute(language, code)` |
| Logfile/CSV/JSON analysieren | `ctx_execute_file(path, language, code)` |
| Datei bearbeiten | Natives `Edit`/`Write` |

---

## Schritt 5: Read / rg / Bash

Erst jetzt. Und nur für den verbleibenden Rest.

---

## Compliance & Enforcement

### Selbst-Check vor Tool-Call

Vor jedem Read/rg/Bash-Call fragst du dich:

> Habe ich code-review-graph für strukturelle Fragen genutzt?
> Habe ich context7 für Library-Fragen konsultiert?
> Habe ich sequential-thinking bei Komplexität ausgeführt?
> Läuft dieser Output durch context-mode?

Wenn eine Antwort "nein" ist und der Schritt relevant war: Pipeline nachholen.

### Abweichungs-Dokumentation

Wenn du einen Schritt überspringst, notiere in der Antwort:

> ℹ️ Schritt X übersprungen: <Grund in max. einem Satz>

Beispiel: "ℹ️ Schritt 2 übersprungen: Reine Config-Datei-Änderung, keine Library-API nötig."
