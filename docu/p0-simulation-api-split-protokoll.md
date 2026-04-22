# P0-Simulation-API-Split-Protokoll

**Start:** 2026-04-22  
**Ziel:** `backend/app/api/simulation.py` kontrolliert, inkrementell und testbar aufspalten, ohne Routing oder Produktverhalten zu brechen.

---

## 1. Ausgangslage

Datei:
- `backend/app/api/simulation.py`

Größe laut Analyse:
- **3251 LOC**

Aktuell enthaltene Route-Gruppen:
- Modell-/Status-Hilfen
- Entity-Read-Endpunkte
- Simulation anlegen / laden / listen
- Prepare-Flow
- Branching
- Profile und Config
- Run Control
- Logs / Actions / Timeline / Posts / Comments
- Interviews
- Env-Steuerung

---

## 2. Split-Strategie

Der Split erfolgt **nicht** als Big Bang, sondern in sicheren Stufen.

### Stufe 1 — sichere, schwach gekoppelte Routen herauslösen
Zuerst werden logisch relativ unabhängige Gruppen extrahiert:

1. `available-models`
2. Entity-Read-Endpunkte
3. grundlegende Lifecycle-Routen:
   - `create_simulation`
   - `get_simulation`
   - `list_simulations`

### Stufe 2 — Helper und gemeinsame Utilities konsolidieren
Danach:
- gemeinsame Kontext-/Storage-Helfer
- gemeinsame Response-/Validation-Patterns

### Stufe 3 — größere Fachblöcke aufteilen
Dann schrittweise:
- Prepare
- Run Control
- Profiles / Config / Branches
- Interviews / Artifacts / Env

---

## 3. Architekturregel für den Split

- Das bestehende Blueprint `simulation_bp` bleibt erhalten.
- Neue Module registrieren ihre Routen auf demselben Blueprint.
- `backend/app/api/__init__.py` importiert die neuen Module zusätzlich.
- Das Verhalten der URL-Pfade bleibt unverändert.

---

## 4. Verifikationsregel

Nach jedem Split-Schritt mindestens:

```bash
cd backend && uv run pytest
cd frontend && npm run build
```

Wenn betroffene P0-Dateien verändert wurden zusätzlich:

```bash
npm run check
```

---

## 5. Laufende Dokumentation

### 5.1 Analyse des Routeninventars
Per AST ausgelesene Route-Gruppen (Auszug):
- `/available-models`
- `/entities/<graph_id>`
- `/entities/<graph_id>/<entity_uuid>`
- `/entities/<graph_id>/by-type/<entity_type>`
- `/create`
- `/prepare`
- `/prepare/status`
- `/<simulation_id>`
- `/list`
- `/history`
- `/<simulation_id>/branch`
- `/<simulation_id>/branches`
- `/<simulation_id>/profiles`
- `/<simulation_id>/config`
- `/start`
- `/stop`
- `/<simulation_id>/pause`
- `/<simulation_id>/resume`
- `/<simulation_id>/run-status`
- `/interview`
- `/env-status`
- `/close-env`

### 5.2 Erste konkrete Zielmodule
Für Stufe 1 werden folgende neuen Module vorgesehen:
- `backend/app/api/simulation_common.py`
- `backend/app/api/simulation_entities.py`
- `backend/app/api/simulation_lifecycle.py`

Diese Auswahl ist bewusst konservativ und risikoarm.
