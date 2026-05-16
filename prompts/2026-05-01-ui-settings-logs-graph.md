# UI/UX Bundle: Settings, Logs, Simulation-Feed, Tool-Panel, Graph

Erstellt: 2026-05-01
Slice-Bündel: Settings-UI + Log-Viewer + Simulation-Feed + Tool-Panel + Graph-DE/Lesbarkeit
Repo: https://github.com/arn0ld87/agora

## Issue-Liste (Reihenfolge nach Risiko, klein → groß)

1. [#129](https://github.com/arn0ld87/agora/issues/129) — Graph: deutsche Beziehungslabels + Lesbarkeit beim Aufbau
2. [#130](https://github.com/arn0ld87/agora/issues/130) — Simulation-Feed: größer, lesbar, Sticky-Scroll ohne Auto-Bottom-Hijack
3. [#131](https://github.com/arn0ld87/agora/issues/131) — Tool-Call/Error-Panel: standardmäßig collapsed + Toggle/Hotkey
4. [#132](https://github.com/arn0ld87/agora/issues/132) — Backend-Log-Viewer (error.log) on demand im Frontend
5. [#133](https://github.com/arn0ld87/agora/issues/133) — Settings-UI: alle .env-Werte zur Laufzeit konfigurierbar (Override-Layer)

Wiederverwendung: Composable `useStickyScroll` aus #130 wird in #131 (Tool-Panel) und #132 (Log-Drawer) genutzt — daher #130 vor #131 und #132 implementieren.

---

## Master-Prompt (an Claude Code, für die ganze Bündelung)

```text
Du arbeitest am Repo Agora (privates OSS, kein IHK-Projekt, keine externe Deadline).
Du implementierst die UI/UX/Settings-Bundle-Slice. Halte dich strikt an unsere Konventionen:

KONVENTIONEN
- Slice-Workflow: jeder Sub-Slice = 1 Commit. `npm run check` muss vor jedem Commit grün sein.
- Doku in `docs/2026-05-01-ui-settings-logs-graph-arbeitsprotokoll.md`. Pro Sub-Slice ein Eintrag (Was/Warum/Tests).
- CHANGELOG.md → Block `[Unreleased]` pflegen.
- Issue-Verlinkung im Commit (`Closes #N`).
- Sicherheitsstandard: keine Secrets in Logs/Responses; Auth-Header für alle neuen `/api/*`.
- Sprache im UI: DE primär, i18n-Strings für jede neue Beschriftung.
- Keine .env überschreiben. Settings-UI nutzt Override-Layer.

REIHENFOLGE (kleinste Risiko-Pfade zuerst)
1. #129 Graph-Lesbarkeit + DE-Labels (rein FE, niedriges Risiko)
2. #130 Simulation-Feed (rein FE; liefert die Sticky-Scroll-Composable)
3. #131 Tool-Panel toggleable (rein FE; nutzt Composable aus #130)
4. #132 Log-Viewer (FE+BE, neue Route, Auth; nutzt Composable aus #130)
5. #133 Settings-UI (FE+BE, größter Scope, getrennt vorbereiten)

VOR JEDEM ISSUE
- Lies das verlinkte Issue komplett.
- Schreibe einen Mini-Plan in `docs/...arbeitsprotokoll.md` (3–8 Bulletpoints).
- Lege Sub-Slices fest. Jeder Sub-Slice hat ein klar testbares Ziel.

WÄHREND DER ARBEIT
- Erst Tests/Akzeptanzkriterien prüfen, dann Code.
- Keine Refactorings nebenbei. Keine Backwards-Compat-Hacks.
- Bei UI-Änderungen: Dev-Server starten und Feature im Browser durchklicken (Golden Path + 1 Edge Case).

ABSCHLUSS-CHECK PRO ISSUE
- npm run check grün
- CHANGELOG `[Unreleased]` ergänzt
- docu-Eintrag aktualisiert
- Commit-Message enthält `Closes #N`
- Kurzer Status-Report: was geändert, welche Tests laufen, was offen ist.

START
Beginne mit dem Graph-Issue nach dem oben skizzierten Schema. Bevor du Code schreibst, präsentiere mir den Sub-Slice-Plan zur kurzen Bestätigung.
```

---

## Per-Issue Ausführungs-Prompts

### Prompt: Graph DE-Labels + Lesbarkeit

```text
Implementiere das Issue „Graph-Beziehungslabels DE + Lesbarkeit" nach unserem Slice-Workflow.

KONTEXT
- Vue 3 Frontend.
- Relevante Dateien: frontend/src/components/GraphPanel.vue, Step1GraphBuild.vue, graph/GraphHints.vue.
- AGENT_LANGUAGE=de wird bereits backend-seitig genutzt; Edge-Type-Strings im Graph kommen heute roh aus Neo4j (vermutlich englisch).

AUFGABE
1. Lies die genannten Dateien und identifiziere die Stelle, an der Edge-Labels gerendert werden.
2. Lege i18n-Map an (frontend/src/i18n/edgeTypes.de.json + en.json). Fallback = Original.
3. Render-Pipeline: vor dem Rendern Label durch i18n-Hook; Persistenz in Neo4j unverändert.
4. UI-Lesbarkeit: Pillen-Hintergrund, min. 12px, Hover-Reveal bei dichten Stellen, Pause-Knopf der Aufbau-Animation.
5. Tests: 1 Snapshot/Komponententest, dass deutscher Label angezeigt wird, wenn locale=de.
6. Akzeptanzkriterien des Issues durchgehen und abhaken.

OUTPUT
- Sub-Slice-Plan (3–6 Punkte) zuerst zur Bestätigung.
- Danach Implementation Sub-Slice für Sub-Slice mit je einem Commit.
```

### Prompt: Simulation-Feed Sticky-Scroll

```text
Implementiere das Issue „Simulation-Feed größer + Sticky-Scroll".

KERNPUNKT „Sticky Scroll"
- Auto-Scroll greift nur, wenn `scrollTop + clientHeight >= scrollHeight - 32`.
- Sobald Nutzer hochscrollt: Auto-Scroll AUS; Banner mit Counter neuer Posts; Klick = scroll-to-bottom + Auto-Scroll wieder AN.
- Implementier das in einer eigenen Composable `useStickyScroll(containerRef)`.

WEITERE PUNKTE
- Layout-Anpassungen wie im Issue beschrieben (≥60% Viewport-Höhe, Min-Höhe 480px, ≤960px Breite, Density-Toggle).
- Komponenten-Extraktion `SimulationFeed.vue` aus Step3Simulation.vue, wenn Step3 dadurch sauberer wird (sonst lassen).
- Playwright-Test im Repo-Stil ergänzen: hochscrollen → neue Posts injizieren → kein Auto-Scroll.

OUTPUT
- Sub-Slice-Plan zuerst, dann committen.
```

### Prompt: Tool-Panel toggleable

```text
Implementiere das Issue „Tool-Call/Error-Panel toggleable".

WICHTIG
- Standard: collapsed.
- Persistenz in localStorage `agora.ui.toolPanel.open`.
- Hotkey Ctrl+L (mit `event.preventDefault()`).
- Badge zählt nur ungesehene Errors. „Gesehen" = Panel war seit letztem Error mind. 1× geöffnet.
- Sticky-Scroll-Composable aus Feed-Issue wiederverwenden, nicht parallel implementieren.

OUTPUT
- Sub-Slice-Plan, dann committen.
```

### Prompt: Backend-Log-Viewer

```text
Implementiere das Issue „Backend-Log-Viewer (error.log) on demand".

BACKEND
- Datei `backend/app/api/logs.py` mit Routes `GET /api/logs`, `GET /api/logs/stream` (SSE).
- Whitelist hardcoded: {"error.log", "app.log"}; Pfade über `Path(LOG_DIR) / name` mit `resolve()` + `is_relative_to(LOG_DIR)`.
- Auth wie bestehende `/api/*`-Routes.
- Streaming: `text/event-stream`, Heartbeat alle 15s, sauberer Abbau bei Disconnect.

FRONTEND
- `LogDrawer.vue` + globaler Store-Flag `ui.logDrawer.open`.
- Sticky-Scroll-Composable aus Feed-Issue wiederverwenden.
- Level-Filter clientseitig (ERROR/WARN/INFO/DEBUG), Suchfeld, Pause-Auto-Scroll.

TESTS
- Backend: 401 ohne Token; 200 mit Token; Path-Traversal-Versuch (`?file=../../etc/passwd` falls je ein Param eingeführt würde) → 400.

OUTPUT
- Sub-Slice-Plan, dann committen.
```

### Prompt: Settings-UI mit Runtime-Override

```text
Implementiere das Issue „Settings-UI für .env-Werte zur Laufzeit".

ARCHITEKTUR
- Lade-Reihenfolge: Defaults → .env → backend/instance/settings.json → in-memory Override (von Tests/Hotswap).
- Quelle pro Feld in der Response (`source: "env"|"file"|"default"|"override"`).
- Pydantic-Schema einmalig definieren, Reuse für Startup-Validierung.
- Secret-Felder explizit markieren (Schema-Metadaten); GET liefert nur `is_set: true|false`.
- PUT mit Atomic-Write (tmp+rename) auf settings.json.

FRONTEND
- `SettingsView.vue` mit Sektions-Tabs (LLM, Neo4j, Embedding, Ontology, Hybrid Search, Agent Tools, Event Bus, Logging, Locale, Webtools, OASIS).
- Pro Feld: Label, Hilfetext (aus Schema), Default, aktuelle Quelle, „Reload erforderlich"-Badge.
- Secrets: separate Maske mit Bestätigung („überschreiben?").

TESTS
- Backend: VECTOR_DIM/EMBEDDING_MODEL-Mismatch → 422 mit klarer Fehlermeldung.
- Backend: Secrets nie im GET-Response als Klartext.
- Frontend: e2e-Smoke „LLM_MODEL_NAME ändern → in GET sichtbar".

OUTPUT
- Sub-Slice-Plan zuerst (mind. 4 Sub-Slices), dann committen.
```
