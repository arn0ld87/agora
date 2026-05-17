# Sub-Slice 24 — Compare API (Layer 7, Closes #66)

**Datum:** 2026-05-05  
**Closes:** [#66](https://github.com/arn0ld87/agora/issues/66)  
**Refs:** #65 (Spike-Doku), #67 (UI-Folge-Slice)  
**Branch:** `feat/layer-7-task-24-compare-api`

---

## Was wurde gebaut

### Service (`backend/app/services/compare_service.py`, NEU)

Klasse `CompareService` mit Dependency-Injection für:
- `network_analytics` (NetworkAnalyticsService)
- `report_reader` (ReportManager)
- `neo4j_storage` (Neo4jStorage)
- `simulation_manager` (SimulationManager)

Methode `compare_branches(simulation_id, branch_a_id, branch_b_id, window_size_rounds) -> BranchComparison` in 4 Schritten:

1. Branch-Resolution + Statusprüfung über `SimulationManager.get_simulation()`
2. `_build_metrics()` aggregiert Netzwerk (via `SimulationRunner.get_all_actions` + `NetworkAnalyticsService.compute_metrics`), Report (via `ReportManager.get_report_by_simulation`), Persona-Reach (via Neo4j-Cypher-Query)
3. `_compute_deltas()` berechnet B − A, ID-basiertes Cluster-Matching
4. Rückgabe als validiertes `BranchComparison`-Pydantic-Objekt

Custom Exceptions: `BranchNotFoundError`, `BranchIncompleteError`

### API-Route (`backend/app/api/simulation_compare.py`, NEU)

Route hängt am bestehenden `simulation_bp` (kein neuer Blueprint):

```
GET /api/simulation/<sim_id>/compare?branch_a=<id>&branch_b=<id>[&window_size_rounds=<int>]
```

Validierungen vor Service-Aufruf: `validate_simulation_id()` für `sim_id`, `branch_a`, `branch_b`. Gleiche IDs → 400. Error-Mapping: `BranchNotFoundError` → 404, `BranchIncompleteError` → 422. Layer-0-Boundary via `BranchComparison.model_validate(comparison.model_dump())` in der Response.

### Blueprint-Registrierung (`backend/app/api/__init__.py`, geändert)

`from . import simulation_compare` ergänzt nach `simulation_metrics`.

### Tests

- `backend/tests/services/test_compare_service.py` (NEU): 7 Tests
- `backend/tests/api/test_simulation_compare.py` (NEU): 10 Tests

---

## Spike-Offene-Fragen (§ 6 des Spike-Dokuments)

### § 6.1 Persona-Segmente
**Entschieden:** Segmente kommen aus `p.segment`-Property der Persona-Knoten in Neo4j. Entspricht der PersonaQuotaPlan-Pipeline (Segment-Property wird beim Profil-Generieren gesetzt). Keine Hardcodierung.

### § 6.2 Window-Sliding
**Entschieden:** `window_size_rounds` wird durchgereicht zu `NetworkAnalyticsService.compute_metrics`. Wird nicht auf Report-Felder (Confidence-Distribution, Evidence) angewendet — diese sind statisch nach Simulation. Konsistent mit Spec.

### § 6.3 Cluster-Matching
**Entschieden:** ID-basiert. Cluster mit gleicher `cluster_id` in beiden Branches → `clusters_changed`. Cluster nur in einem Branch → `clusters_only_in_a/b`. Semantic-Similarity-Matching ist Out of Scope für v1 (explizit in Spike dokumentiert).

### § 6.4 Single-Number-Score
**Offen, Out of Scope:** Kein `weighted_avg_confidence`-Score in v1. Verbleibt als Aufgabe für #67 (Compare-UI) falls Frontend einen Summary-Score braucht.

### § 6.5 Contradiction-Penalty
**Entschieden:** Aus `claim.audit_trail.contradiction_detected` gelesen. Default `0.0` wenn Audit-Trail nicht live. Hook ist im Code verdrahtet, liefert `0.0` bis Evidence-Binder ihn befüllt.

### § 6.6 Performance / Caching
**Entschieden:** Kein Caching in v1. Timeout-Handling über `handle_api_errors`-Decorator (→ 504). Bei großen Simulationen kann die Neo4j-Persona-Reach-Query teuer werden; Pre-Aggregation als Folge-Slice dokumentiert.

---

## Akzeptanz-Snapshots

```
rg-Output "compare_service" backend/app/api/__init__.py:
  from . import simulation_compare  # -- Sub-Slice 24 (#66): Branch-Compare-API

pytest -x -q: 1512 passed, 9 skipped
neue Tests: 17 passed (7 service + 10 api)
ruff check app/ tests/: All checks passed!
mypy app/services/compare_service.py app/api/simulation_compare.py: Success
git diff --exit-code schemas/: Exit 0 (idempotent)
```
