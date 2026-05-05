# Arbeitsprotokoll: Sub-Slice 22 — GET /api/graph/<graph_id>/diff (Closes #74)

**Datum:** 2026-05-05
**Branch:** claude/modest-kapitsa-26d24a
**Worker:** agora-refactor-worker (Sonnet)

---

## Was geändert wurde

### Neue Datei: `backend/app/utils/graph_diff_helpers.py` (+170 LOC)

Zustandslose Hilfsfunktionen für die Konvertierung von `TemporalGraphService`-Dataclasses in Pydantic-Layer-0-Contracts:

- `_edge_to_contract(edge: dict) -> EdgeData` — edge-Dict (aus Neo4j-Storage) → EdgeData, filtert interne Felder aus properties
- `_reinforced_to_contract(r: dict) -> EdgeReinforcement` — reinforcement-Dict → EdgeReinforcement, stellt weight_after >= weight_before sicher
- `_snapshot_to_contract(snap, graph_id, round_num) -> GraphSnapshot` — Service-GraphSnapshot → Pydantic-GraphSnapshot (node_count aus edge-Analyse geschätzt, Phase-2-Felder als Defaults)
- `_compute_metrics(...) -> GraphDiffMetrics` — berechnet aggregierte Metriken aus Diff-Listen
- `build_pydantic_graph_diff(service_diff, snap_a, snap_b, graph_id, start_round, end_round) -> GraphDiff` — zentraler Assembler, ruft alle Hilfsfunktionen auf

### Geänderte Datei: `backend/app/api/graph.py` (+42 / -19 LOC netto)

**Route-Änderung (Breaking Change, absichtlich):**
- Alt: `GET /diff/<graph_id>` → Neu: `GET /<graph_id>/diff`
- Entspricht der REST-Ressourcen-Semantik: `/<graph_id>` ist die Ressource, `/diff` ist die Sub-Aktion

**Neue Fehlerbehandlung:**
- Fehlende `start_round`/`end_round` → 400 VALIDATION_FAILED (statt alter Fallback auf 0)
- Negative Runden → 400 VALIDATION_FAILED
- `end_round < start_round` → 400 VALIDATION_FAILED (war schon vorhanden, bleibt)

**Layer-0-Boundary:**
- `build_pydantic_graph_diff()` baut PydanticGraphDiff auf
- `graph_diff.model_dump(mode="json")` serialisiert für die Response
- Kein `diff.to_dict()` mehr — vollständige Validierung via Pydantic

**Neuer Import:**
- `from ..utils.graph_diff_helpers import build_pydantic_graph_diff`

### Geänderte Datei: `backend/tests/api/test_graph_endpoints.py` (+0 / -0 LOC, Route-URLs angepasst)

Zwei bestehende Tests nutzten die alte Route `/diff/<graph_id>`. Auf `/graph_id>/diff` umgestellt:
- `test_get_graph_diff_invalid_id_returns_invalid_id_code`
- `test_get_graph_snapshot_negative_round_returns_validation_failed`
- `test_get_graph_diff_non_integer_rounds_returns_validation_failed`

### Neue Datei: `backend/tests/test_graph_diff_api.py` (+160 LOC, 5 Tests)

HTTP-Level-Tests mit Flask-Test-Client + StubStorage (kein Neo4j):

1. `test_diff_returns_200_with_valid_graph_diff_structure` — 200, Layer-0-Boundary via `PydanticGraphDiff.model_validate()`
2. `test_diff_missing_params_returns_400` — fehlende Parameter → 400 validation_failed
3. `test_diff_invalid_round_order_returns_400` — start > end → 400
4. `test_diff_snapshot_a_b_have_expected_fields` — alle Top-Level-Felder vorhanden, snapshot_a_id != snapshot_b_id
5. `test_diff_same_round_returns_empty_diff` — start == end → leere added/removed/reinforced Listen

### Geänderte Datei: `backend/tests/test_temporal_graph.py` (+35 LOC, 1 neuer Test)

- `test_compute_diff_added_edges_tracked` — verifiziert `_edge_to_contract()`: uuid, source_id, target_id, weight, reinforced_count korrekt gemappt; interne Felder (`valid_from_round`, `graph_id`) nicht in properties; extra-bools in properties

---

## Konvertierungsstrategie (Dataclass → Pydantic)

Der `TemporalGraphService` gibt Service-seitige Dataclasses zurück:
- `service.GraphDiff` mit `.added`, `.removed`, `.reinforced` (je `list[dict]`)
- `service.GraphSnapshot` mit `.edges` (ebenfalls `list[dict]`)

Da die Service-Dataclasses deutlich flacher sind als der Pydantic-Contract (kein `metrics`, keine `cluster_shifts`, keine `bridge_agents`), wird die Konvertierung in `graph_diff_helpers.py` isoliert, statt in graph.py inline zu stehen.

**Validierungs-Invariante für EdgeReinforcement:** Der Pydantic-Contract erzwingt `weight_after >= weight_before`. Da TemporalGraphService `reinforced_count` (int) als Proxy für Gewicht führt, aber kein echtes `weight_before`/`weight_after` kennt, wird im Fehlerfall `weight_after = weight_before + delta_rc` gesetzt (delta_rc = rc_after - rc_before > 0). Das garantiert, dass der Validator nicht reißt.

---

## Phase-2-Hinweise (Felder noch leer)

Folgende Felder sind in dieser Phase mit Defaults befüllt:

| Feld | Default | Phase-2-Quelle |
|---|---|---|
| `cluster_count` | 0 | Louvain-Clustering via NetworkAnalyticsService |
| `dominant_clusters` | [] | Top-k Cluster nach Louvain |
| `bridge_agents` | [] | Betweenness-Centrality Top-k |
| `cluster_shifts` | [] | Louvain A vs. B |
| `bridge_agent_shifts` | [] | Centrality-Delta A vs. B |
| `node_properties_changed` | [] | Node-Property-Diff via Neo4j |
| `edges_weakened` | [] | TemporalGraphService kennt noch keine Abschwächungs-Logik |
| `metrics.agents_changed_clusters` | 0 | Phase-2 |
| `metrics.clusters_new/removed` | 0 | Phase-2 |
| `metrics.bridge_agents_joined/left` | 0 | Phase-2 |
| `metrics.node_properties_changed` | 0 | Phase-2 |
| `node_count` im Snapshot | aus edges geschätzt | Phase-2: eigene Node-Storage-Abfrage |

---

## Test-Ergebnis

```
# Neu/geänderte Tests:
75 passed in 1.53s  (contracts + test_graph_diff_api + test_temporal_graph)

# Vollsuite (außer llm-Marker):
1495 passed, 9 skipped, 7 deselected in 78.98s

# ruff check app/ tests/:
4 errors auto-fixed, 0 remaining

# mypy app/utils/graph_diff_helpers.py app/api/graph.py:
Success: no issues found in 2 source files

# Schema-Dump:
10 schemas OK, git diff --exit-code schemas/ → kein Drift
```

---

## LOC-Delta Zusammenfassung

| Datei | +LOC | -LOC | Status |
|---|---|---|---|
| `app/utils/graph_diff_helpers.py` | +170 | 0 | neu |
| `app/api/graph.py` | +54 | -19 | geändert |
| `tests/test_graph_diff_api.py` | +160 | 0 | neu |
| `tests/test_temporal_graph.py` | +37 | 0 | geändert |
| `tests/api/test_graph_endpoints.py` | +3 | -3 | route-URLs |
| `CHANGELOG.md` | +1 | 0 | geändert |
