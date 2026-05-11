# P0-Protokoll — Simulation-/Polling-JSON-Härtung

**Datum:** 2026-04-23

---

## 1. Anlass

Nach dem Fix für die Report-Status-Regression wurde geprüft, ob ähnliche Race-Conditions auch in anderen Polling-Pfaden auftreten können.

Besonders kritisch sind dabei JSON-Artefakte, die gleichzeitig:
- von Backend-Prozessen geschrieben werden
- und von Frontend-Polling-Endpunkten gelesen werden

Typische Kandidaten:
- `state.json`
- `run_state.json`
- `simulation_config.json`
- `reddit_profiles.json`
- `meta.json`

---

## 2. Ziel

Die Simulation-nahe Dateiverarbeitung sollte robuster werden, ohne die bestehende file-based Architektur auszutauschen.

Konkret:
1. JSON-Schreibzugriffe atomisieren
2. JSON-Lesezugriffe defensiv machen
3. Polling-Endpunkte sollen bei kurzzeitig unlesbaren Dateien degradiert weiterlaufen statt 500 zu werfen

---

## 3. Neue gemeinsame Hilfsdatei

### `backend/app/utils/json_io.py`

Eingeführt wurden zwei kleine Helfer:
- `write_json_atomic(path, payload)`
- `read_json_file(path, default=..., logger=..., description=...)`

**Nutzen:**
- Schreibvorgänge laufen über Temp-Datei + `os.replace(...)`
- Lesevorgänge tolerieren fehlende, leere oder temporär trunkierte Dateien und liefern stattdessen einen definierten Default

---

## 4. Gehärtete Bereiche

### 4.1 `backend/app/services/simulation_runner.py`
- `run_state.json` wird atomisch geschrieben
- `run_state.json` wird defensiv gelesen
- Status-Update von `state.json` beim Cleanup ist jetzt robuster

### 4.2 `backend/app/services/simulation_manager.py`
- `state.json` wird atomisch geschrieben
- `state.json`, `simulation_config.json`, `reddit_profiles.json` und Report-Meta-Lookups lesen defensiver
- Branch-Config wird atomisch geschrieben

### 4.3 `backend/app/api/simulation_prepare.py`
- `_check_simulation_prepared()` reagiert sauber auf temporär unlesbare `state.json`
- Auto-Update von `preparing -> ready` schreibt atomisch

### 4.4 `backend/app/api/simulation_profiles.py`
- realtime profile/config polling liest defensiver
- reddit profile writes laufen atomisch

### 4.5 `backend/app/api/simulation_history.py`
- Report-Meta-Lookup für History toleriert temporär unlesbare `meta.json`

---

## 5. Verifikation

### Targeted Ruff
Befehl:
```bash
cd backend && uv run ruff check app/api/simulation_prepare.py app/api/simulation_profiles.py app/api/simulation_history.py app/services/simulation_manager.py app/services/simulation_runner.py app/utils/json_io.py
```

Ergebnis:
- **bestanden**

### Targeted Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_runtime.py tests/test_simulation_api_routes.py tests/test_report_manager.py tests/test_embedding_service.py
```

Ergebnis:
- **24/24 bestanden**

### Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **70 bestanden**
- Frontend Lint → **0 Fehler, 21 Warnungen**
- Frontend Build → **bestanden**

---

## 6. Bewertung

Die App bleibt weiter bewusst dateibasiert, aber die wichtigsten Polling-Dateien sind jetzt deutlich robuster gegen Timing-Fenster zwischen Schreiben und Lesen.

Das ist kein kompletter Architekturwechsel, aber ein wichtiger Stabilitätsschritt:
- weniger sporadische 500er
- weniger JSONDecode-Races
- besseres Verhalten unter aktivem UI-Polling
