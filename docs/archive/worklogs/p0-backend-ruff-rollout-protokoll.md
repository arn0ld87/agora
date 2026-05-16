# P0-Protokoll — Backend-Ruff-Rollout Phase 2

**Datum:** 2026-04-23

---

## 1. Ziel

Nach der ersten Qualitätsbasis und den späteren gezielten Ruff-Erweiterungen war der nächste sinnvolle Schritt ein weiterer **low-risk Ruff-Rollout** auf unkritische Backend-Module und Testdateien.

Es ging dabei bewusst **nicht** um ein Full-Repo-`ruff check .`, sondern um den nächsten stabilen Cluster mit geringem Migrationsrisiko.

---

## 2. Neuer gesäuberter Modulblock

### Backend-Module
- `backend/app/api/runs.py`
- `backend/app/services/graph_memory_updater.py`
- `backend/app/utils/gpu_probe.py`
- `backend/app/storage/search_service.py`

### Tests
- `backend/tests/test_status.py`
- `backend/tests/test_logging.py`
- `backend/tests/test_neo4j_resilience.py`

---

## 3. Art der Fixes

Es wurden nur low-risk Ruff-Fixes umgesetzt:
- ungenutzte Imports entfernt
- ungenutzte Variablen bereinigt oder umbenannt
- triviale Namensverbesserungen in Tests
- keine fachliche Verhaltensänderung

---

## 4. Scope-Erweiterung

Die gesäuberten Dateien wurden anschließend in die gescopten Ruff-Listen aufgenommen:
- `package.json`
- `.github/workflows/ci.yml`

Damit sind sie ab jetzt Teil des regulären lokalen und CI-Lint-Gates.

---

## 5. Verifikation

### Targeted Ruff
Befehl:
```bash
cd backend && uv run ruff check app/api/runs.py app/services/graph_memory_updater.py app/utils/gpu_probe.py app/storage/search_service.py tests/test_status.py tests/test_logging.py tests/test_neo4j_resilience.py
```

Ergebnis:
- **bestanden**

### Targeted Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_status.py tests/test_logging.py tests/test_neo4j_resilience.py
```

Ergebnis:
- **23/23 bestanden**

---

## 6. Bewertung

Dieser Schritt bringt das Projekt noch nicht auf Full-Repo-Ruff-Niveau, erweitert aber den sicheren Kern weiter.

Wichtig ist vor allem:
- neue stabile Module und Tests sind nun standardmäßig im Quality-Gate
- der Abstand zwischen aktuellem Zustand und echtem `ruff check .` wird kleiner
- der Rollout bleibt beherrschbar, weil nur risikoarme Dateien aufgenommen wurden
