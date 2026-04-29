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
