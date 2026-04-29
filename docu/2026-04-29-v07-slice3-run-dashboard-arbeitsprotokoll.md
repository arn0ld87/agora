# v0.7 Slice 3 — Run Dashboard Arbeitsprotokoll

Datum: 2026-04-29
Repo: `/mnt/brain/Projekte/Agora`
Branch: `main`
Vorgaenger-Slice: 2 (Persona Review Foundation, abgeschlossen mit Commit `5eb9703`).

## Ziel

Slice 3 aus `docu/2026-04-29-v07-umsetzungsplan.md` macht bestehende Runs zentral sichtbar und nachvollziehbar. Die `/api/runs`-API wird erweitert (nicht ersetzt), das Frontend bekommt eine eigene Run-Dashboard-View, der Detail-Drawer wird poliert. Mutierende Aktionen wie Delete oder Duplicate bleiben raus, weil die Semantik laut Plan ungeklaert ist.

## Sub-Slice-Schnitt

Wegen Groesse von Slice 3 wird der Block in drei Unter-Slices zerlegt (bestaetigt mit Nutzer):

1. **3.1 Backend-Erweiterung** (dieses Protokoll) — `entity_id`-Filter durchreichen, Detail-/List-Endpoints um abgeleitete Summary-Felder anreichern, Pytest-Suite fuer `/api/runs`.
2. **3.2 Frontend Run-Dashboard-View** — `RunsView.vue` als Route `/runs`, Tabelle erweitert um Datum, Modell, Dokument, Graph-Name, Persona-Anzahl.
3. **3.3 Detail-Drawer-Polish** — Fehler-Block separat, Artefakte als klickbare Pfade, mutierende Aktionen guarded.

## 3.1 — Backend-Erweiterung

### Vorgehen

1. Inventur der bestehenden Run-API ([backend/app/api/runs.py](../backend/app/api/runs.py), [run_registry.py](../backend/app/services/run_registry.py), [HistoryDatabase.vue](../frontend/src/components/HistoryDatabase.vue)). Ergebnis:
   - Liste/Detail/Events/Stop/Resume sind bereits implementiert.
   - `entity_id`-Filter existiert in `RunRegistry.list_runs`, wird aber in der Route nicht durchgereicht — Frontend schickt den Param (siehe `HistoryDatabase.vue:54`), er versickert.
   - Manifest enthaelt `linked_ids` + `metadata` (graph_id, branch_name, graph_name), liefert aber **nicht** Modell, Dokument-Name, Persona-Anzahl. Diese Daten leben in `simulation_config.json`, `Project.files` und `reddit_profiles.json` — aussen am Run-Manifest.
2. Read-Path-Anreicherung statt Persistenz gewaehlt: das Manifest bleibt unveraendert, die abgeleiteten Felder werden beim GET/Liste-Lesen lazy aufgeloest und als `summary`-Block im Response-Envelope angefuegt. So bleibt die Persistenz sortenrein und alte Run-Manifeste brauchen keine Migration.
3. Helper `_build_run_summary` in `runs.py` mit Per-Request-Caches `sim_cache`/`project_cache`, damit eine Liste von 200 Runs nicht 200x dieselben Sim-Configs liest. Defensive-Reads: Fehlende Sim/Project liefern `None`, kein Crash.
4. Persona-Anzahl wird aus `app.extensions['artifact_store']` ueber den `reddit_profiles`-Artefakt gelesen — derselbe Store, den `SimulationManager` via `resolve_default_store()` nutzt. Im Test wird ein `InMemoryArtifactStore` registriert, im Prod ist es der `LocalFilesystemArtifactStore` aus `create_app`.
5. `entity_id` als Query-Param in `list_runs()` durchgereicht (1-Liner, der bestehende `RunRegistry`-Service unterstuetzt es bereits).
6. Pytest-Suite `tests/test_runs_api.py` neu angelegt: 8 Tests gegen die HTTP-Layer (Default-Liste, `entity_id`-Filter, kombinierte Filter, Detail mit Summary, 404 fuer unbekannte Run-IDs, 400 fuer ungueltiges Format, Events-Route, defensiver Summary-Pfad bei verwaister Sim/Project). Setup nutzt `tmp_path` + monkeypatch auf `Config.UPLOAD_FOLDER`, `ProjectManager.PROJECTS_DIR`, `SimulationManager.SIMULATION_DATA_DIR`, `RunRegistry.REGISTRY_DIR` und reset des `RunRegistry`-Singletons.

### Geaenderte/Neue Dateien

| Datei | Aenderung |
|---|---|
| `backend/app/api/runs.py` | `entity_id`-Filter in `list_runs()`; Helper `_resolve_simulation_summary`, `_resolve_project`, `_build_run_summary`, `_attach_summary`; Liste und Detail liefern jetzt einen `summary`-Block (`model`, `document_name`, `persona_count`, `graph_id`, `graph_name`, `branch_name`) |
| `backend/tests/test_runs_api.py` | **Neu**: 8 HTTP-Tests fuer Liste/Filter/Detail/404/400/Events plus Defensive-Pfad |

### Bewusst nicht geaendert

1. `RunRegistry.create_run` / `update_run` — Manifeste bleiben sortenrein, keine neuen persistierten Felder.
2. `Stop`/`Resume`-Routen unangetastet — Verhalten bleibt wie in v0.6.x.
3. `RunRecord`-TS-Type im Frontend bleibt zunaechst, das Anpassen kommt in 3.2 zusammen mit den neuen Tabellen-Spalten.
4. Keine neuen Env-Vars, kein Service-Inventar-Eintrag — `CLAUDE.md`/`AGENTS.md` bleiben unveraendert.

### Verifikation (3.1)

```bash
cd backend && uv run pytest tests/test_runs_api.py -x --no-header
```

Ergebnis: 8 passed in 2.60s.

`npm run check` (Backend-Lint + Pytest gesamt + Frontend-Lint + Vite-Build): siehe Commit-Verifikation.

### Naechste Schritte

- 3.2 Frontend: `RunsView.vue` als Route `/runs`, Tabelle erweitert um Datum-, Modell-, Dokument-, Graph-, Persona-Spalten; TS-Type-Korrekturen (`started_at`, neue Filter-Params).
- 3.3 Drawer-Polish: Fehler-Block, Artefakt-Links, guarded mutierende Aktionen.

## 3.2 — Frontend Run-Dashboard-View

### Vorgehen

1. Inventur: `HistoryDatabase.vue` ist eine Komponente, eingebettet in `Home.vue` als Section "06 Run Center". Eine eigene Route `/runs` existiert bisher nicht, der Wunsch aus dem Plan ist aber ein zentrales Dashboard. Loesung: HistoryDatabase bleibt die einzige Stelle mit der Run-Logik, eine neue `RunsView.vue` haengt sie als Vollbild-View ein, Home behaelt seine Section und bekommt einen "Run-Dashboard oeffnen"-Link.
2. Komponente bekommt eine Prop `showOpenLink` (Default `false`), damit Home den Link zeigt und die dedizierte View nicht.
3. Tabellenzeilen rendern jetzt aus dem `summary`-Block (Slice 3.1): primaere Zeile zeigt `summary.document_name` (Fallback: `message`/`entity_id`), die Sub-Zeile bricht `model · persona_count Personas · graph_name · branch` zusammen — minimal-invasiv, keine zusaetzliche Spalte, kein Layout-Bruch im 5-Spalten-Grid.
4. Detail-Drawer (`.meta-grid`) ergaenzt sechs Felder: Modell, Personas, Dokument, Graph (Name oder Fallback ID), Branch, Started — alle mit `'—'`-Fallback bei fehlenden Werten. So zeigt der Drawer auf einen Blick, was in 3.1 angereichert wurde.
5. TS-Types (`frontend/src/types/run.ts`) auf den realen Backend-Manifest-Stand gebracht:
   - `created_at` (gab es nie) entfernt, dafuer `started_at` (Backend `RunRegistry.create_run`).
   - `error`, `artifacts`, `resume_capability`, `summary` ergaenzt.
   - Neue Interfaces `RunResumeCapability`, `RunArtifacts`, `RunSummary`.
   - `RunEvent` umstrukturiert auf das tatsaechliche Manifest-Format (`timestamp`, `type`, `status`, `progress`, `message`, `error`, `details`).
   - `ListRunsParams` um `project` und `branch` erweitert (Backend kennt sie, Frontend nutzt sie in den Filter-Selects).
6. Neue `RunsView.vue` als Route `/runs` mit dezentem Header (Brand-Link + Zurueck-Button), `<HistoryDatabase :show-open-link="false" />` und `AppFooter`. Bewusst KEIN WorkspaceLayout — Run-Dashboard ist keine Pipeline-Step-View und braucht weder ModeSwitch noch Step-Status.
7. Router (`frontend/src/router/index.js`) bekommt Route `Runs` → `/runs`.

### Geaenderte/Neue Dateien (3.2)

| Datei | Aenderung |
|---|---|
| `frontend/src/types/run.ts` | TS-Types am Backend-Manifest ausgerichtet; neue Interfaces `RunSummary`, `RunArtifacts`, `RunResumeCapability`; `started_at` statt `created_at`; `ListRunsParams` um `project` + `branch` erweitert |
| `frontend/src/components/HistoryDatabase.vue` | Prop `showOpenLink`, Helfer `summaryFor`/`metaLineFor`/`primaryLabelFor`, Sub-Zeile aus Summary, Detail-Drawer um sechs Summary-Felder erweitert, Header-Link auf `/runs` |
| `frontend/src/views/RunsView.vue` | **Neu**: dezidierte `/runs`-Vollbild-View mit Brand-Link, eingebetteter `HistoryDatabase` und `AppFooter` |
| `frontend/src/router/index.js` | Neue Route `Runs` → `/runs` |
| `frontend/src/views/Home.vue` | `HistoryDatabase` mit `:show-open-link="true"` aufgerufen |

### Bewusst nicht geaendert

1. Tabellen-Layout: keine zusaetzlichen Spalten, sondern eine zwei-Zeilen-Variante in der vorhandenen `message`-Zelle — verhindert harte Breakpoints und Layout-Brueche im bestehenden 5-Spalten-Grid.
2. Polling: noch keine Auto-Refresh-Logik. Liste laedt bei Mount, nach `Resume`/`Stop`/`Branch`. Polling kommt ggf. zusammen mit dem 3.3-Drawer-Polish, wenn die Mutationen mehr Live-Feedback brauchen.
3. Mutationen (`Resume`, `Stop`, `Branch`-Form) bleiben unveraendert — Slice 3.3 schiebt sie hinter Confirm-Dialoge bzw. einklappbare "Mehr Aktionen"-Box.
4. WorkspaceLayout-System: bewusst nicht uebernommen. Run-Dashboard ist keine Pipeline-Step-View; das Layout-System ist hier overkill und wuerde unnoetige Abhaengigkeiten ziehen.

### Verifikation (3.2)

```bash
npm run check
```

Ergebnis: Backend-Lint gruen, **264 passed, 2 skipped**, Frontend-Lint gruen, Vite-Build gruen (726 Module, +2 fuer `RunsView.vue` + Run-Type-Update).

### Naechste Schritte

- 3.3 Drawer-Polish: Fehler-Block separat (mit `error`-Feld + Stacktrace falls vorhanden), Artefakte als klickbare Pfade statt JSON-Pre-Block, Resume/Stop hinter `confirm()`-Dialog, Branch-Form einklappbar.
