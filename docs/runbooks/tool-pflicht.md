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

## Schritt 3: ctx_batch_execute (Primary Research)

**Zweck:** Mehrere Befehle + Suchfragen in EINEM Call. Ersetzt 30+ Einzel-Calls.

### Wann Pflicht

Immer wenn du Shell-Befehle oder MCP-Tool-Calls mit potenziell >20 Zeilen Output machst.

### Tool-Wahl

| Szenario | Tool |
|---|---|
| Mehrere Commands + mehrere Suchfragen | `ctx_batch_execute(commands, queries)` — EIN Call |
| Ein Command, große Ausgabe | `ctx_execute(language, code)` |
| Logfile/CSV/JSON analysieren | `ctx_execute_file(path, language, code)` |
| Webseiten fetchen + indexieren | `ctx_fetch_and_index(url, source)` → `ctx_search(queries)` |
| Gezielte Suche in indexierten Inhalten | `ctx_search(queries)` |

### Harte Regel

**ALLER Command-Output > 20 Zeilen MUSS durch `ctx_batch_execute` oder `ctx_execute`.**
Kein Bash für Analysen — Bash NUR für git, mkdir, rm, mv, Navigation.

### Nicht nötig bei

- Edit, Write, mkdir, rm, mv, git add/commit/push (Bash hier okay)
- Kleine Read-Calls (<50KB) zum Editieren

---

## Schritt 4: ctx_execute / ctx_execute_file (Processing)

**Zweck:** Einzel-Analysen, API-Calls, Datenverarbeitung, Datei-Analyse.

### Wann Pflicht

- API-Calls (gh, curl-Ersatz)
- Log-Analyse
- Build-Output verarbeiten
- Große Dateien analysieren (ctx_execute_file statt Read)

### Nicht nötig bei

- Kleine Dateien, die du editieren willst → Read ist korrekt

---

## Schritt 5: Read / Bash

Erst jetzt. Und nur für den verbleibenden Rest.

- **Read:** Nur wenn du die Datei EDITIEREN willst. Analysen → ctx_execute_file.
- **Bash:** NUR git, mkdir, rm, mv, Navigation. Shell-Analysen → ctx_execute.
- **WebFetch:** Erlaubt für kleine Lookups. Research → ctx_fetch_and_index.

---

## Compliance & Enforcement

### Selbst-Check vor Tool-Call

Vor jedem Read/Bash-Call fragst du dich:

> Habe ich code-review-graph für strukturelle Fragen genutzt?
> Habe ich context7 für Library-Fragen konsultiert?
> Läuft dieser Output durch ctx_batch_execute / ctx_execute?
> Ist Bash wirklich nur git/fs/nav?

Wenn eine Antwort "nein" ist und der Schritt relevant war: Pipeline nachholen.

### Abweichungs-Dokumentation

Wenn du einen Schritt überspringst, notiere in der Antwort:

> ℹ️ Schritt X übersprungen: <Grund in max. einem Satz>

Beispiel: "ℹ️ Schritt 2 übersprungen: Reine Config-Datei-Änderung, keine Library-API nötig."
