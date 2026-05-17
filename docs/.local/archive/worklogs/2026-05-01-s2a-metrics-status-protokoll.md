# S2a — Metric-Snapshot Status-Flag · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S2a (Evidence-Pipeline-v2-Initiative)

## Ziel

Statt 0/0/0/0 als „Metriken" auszuweisen, expliziten Status-Flag setzen, plus deterministische `snapshot_id` und `calculated_at` mitliefern.

## Implementierung

`backend/app/services/network_analytics.py`:

- Neue Konstanten `METRICS_STATUS_OK`, `METRICS_STATUS_NO_ACTIONS`, `METRICS_STATUS_NO_PAIRWISE`.
- `PolarizationMetrics` um `snapshot_id`, `calculated_at`, `status` erweitert; `to_dict()` führt sie an erster Stelle.
- `compute_metrics`:
  - generiert `snapshot_id = "metrics_<sha1[12]>"` aus `(simulation_id, len(actions), window, calculated_at)`
  - `calculated_at` als ISO-8601 mit Sekunden-Granularität (UTC)
  - liefert `status="no_actions"`/`"no_pairwise_interactions"`/`"ok"` je nach Datenlage

## Tests (4 neu, alle grün)

- `test_status_no_actions_for_empty_input`
- `test_status_no_pairwise_for_broadcast_only`
- `test_status_ok_when_interactions_present`
- `test_to_dict_includes_status_and_metadata`

499 Backend-Tests grün, 40 Frontend, Build clean.
