# Sub-Slice 33 — /api/runs Erweiterung (Task 26, Layer 7, Closes #62)

**Datum:** 2026-05-03
**Branch:** `feat/layer-7-task-26-runs-api`
**Status:** implementiert, Tests grün

---

## Recherche-Notizen

### Status-Werte aus dem Storage

`RunRegistry.canonical_status()` (`backend/app/services/run_registry.py:47-67`) normalisiert alle Roh-Inputs auf folgende kanonische Ausgabewerte:

| Kanonisch | Roh-Inputs (werden intern gemappt) |
|---|---|
| `pending` | pending, idle, not_started, created |
| `processing` | processing, running, planning, generating, starting, preparing |
| `paused` | paused |
| `completed` | completed, ready |
| `failed` | failed |
| `stopped` | stopped, stopping |

**Kein** `running`, `queued` oder `cancelled` auf API-Ebene — die Registry normalisiert.

### Existierender Stand von `GET /api/runs`

Vor diesem Slice:
- Filter: `project`, `run_type`, `status` (Single), `branch`, `entity_id`
- Limit: max 200, kein Offset
- Kein `simulation_id`-Filter
- Kein `since`-Filter
- Keine Status-Aggregation
- Response: Plain-List (kein typisierter Wrapper)

### Frontend `frontend/src/types/run.ts`

Bereits konform mit den kanonischen Status-Werten. `ListRunsParams` hatte bereits
`status` und `entity_id`, aber kein `simulation_id`, `since`, `offset`, `aggregate`.

---

## Geänderte Dateien

### Neu

| Datei | LOC | Inhalt |
|---|---|---|
| `backend/app/contracts/runs_contract.py` | 75 | Pydantic: RunStatus, RunSummary, RunDetail, RunsAggregation, RunsListResponse, RunsFilterQuery |
| `backend/tests/api/test_runs_api_filter_aggregate.py` | 238 | 10 Tests (9 Szenarien + 1 Detailtest) |
| `frontend/src/contracts/runsContract.ts` | 91 | Zod-Spiegel zu den Pydantic-Contracts |
| `schemas/run-summary.schema.json` | auto | Schema-Dump |
| `schemas/runs-list-response.schema.json` | auto | Schema-Dump |
| `schemas/run-detail.schema.json` | auto | Schema-Dump |

### Geändert

| Datei | Änderung |
|---|---|
| `backend/app/contracts/__init__.py` | Re-Export: RunStatus, RunSummary, RunDetail, RunsAggregation, RunsListResponse, RunsFilterQuery |
| `backend/app/contracts/dump_schemas.py` | 3 neue Einträge in CONTRACTS-Dict |
| `backend/app/api/runs.py` | list_runs: Pydantic-Query-Validierung, Offset, Since, Simulation-ID-Filter, Aggregation; get_run: RunDetail + live metrics (_build_run_detail) |
| `backend/app/services/run_registry.py` | list_runs: statuses (Multi), since, offset, simulation_id Parameter; aggregate_by_status() Methode |
| `backend/tests/test_runs_api.py` | 3 List-Tests auf neue `data["runs"][...]`-Shape angepasst |

---

## Neue Query-Parameter für GET /api/runs

| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `status` | `RunStatus` (mehrfach oder kommagetrennt) | — | Filter auf Status(se) |
| `simulation_id` | `str` | — | Filter auf Simulation |
| `since` | ISO-8601 | — | Nur Runs mit `updated_at >= since` |
| `limit` | int 1–200 | 50 | Maximale Anzahl Ergebnisse |
| `offset` | int ≥ 0 | 0 | Paginierungs-Offset |
| `aggregate` | `"status"` | — | Status-Aggregation beilegen |

Bestehende Parameter (`project`, `run_type`, `branch`, `entity_id`) weiterhin gültig.

### GET /api/runs/<id> — neue Felder

| Feld | Typ | Quelle |
|---|---|---|
| `eta_seconds` | `int \| null` | `run.metadata.eta_seconds` |
| `log_tail` | `list[str] \| null` | Letzte 20 Event-Messages |
| `metrics` | `dict \| null` | phase/round_num/last_event_at aus Metadata/Events |

---

## Schema-Dump-Output

```
✓ schemas/report-contract.schema.json  (unverändert)
✓ schemas/report.schema.json           (unverändert)
✓ schemas/evidence-map.schema.json     (unverändert)
✓ schemas/persona.schema.json          (unverändert)
✓ schemas/persona-quota-plan.schema.json (unverändert)
✓ schemas/run-summary.schema.json      (NEU)
✓ schemas/runs-list-response.schema.json (NEU)
✓ schemas/run-detail.schema.json       (NEU)
```

`git diff --exit-code schemas/` = exit 0 (keine Drift in bestehenden Schemas).

---

## Test-Ergebnis

```
tests/api/test_runs_api_filter_aggregate.py::test_list_default... PASSED
tests/api/test_runs_api_filter_aggregate.py::test_filter_by_single_status PASSED
tests/api/test_runs_api_filter_aggregate.py::test_filter_by_simulation_id PASSED
tests/api/test_runs_api_filter_aggregate.py::test_filter_by_since PASSED
tests/api/test_runs_api_filter_aggregate.py::test_aggregate_status_returns_counts PASSED
tests/api/test_runs_api_filter_aggregate.py::test_pagination_limit_offset PASSED
tests/api/test_runs_api_filter_aggregate.py::test_limit_cap_returns_400 PASSED
tests/api/test_runs_api_filter_aggregate.py::test_get_run_detail_has_live_metric_fields PASSED
tests/api/test_runs_api_filter_aggregate.py::test_get_run_detail_null_live_metrics_when_absent PASSED
tests/api/test_runs_api_filter_aggregate.py::test_invalid_status_returns_400 PASSED

Gesamt: 1296 passed, 9 skipped (davon 7 Docker-Compose-Skip, 2 Redis-Skip)
```

---

## Performance-Hinweis

Filter und Aggregation laufen in-memory über alle JSON-Manifest-Dateien im
`run_registry/`-Verzeichnis. Zeitkomplexität: O(n) pro Request. Bei > 10.000 Runs
ist ein DB-Index (Neo4j oder SQLite) zu erwägen — jetzt aber kein Engpass.
