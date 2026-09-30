### Changed (Simulation: Feed-Verträge und Aktionsprotokoll-Endpoints abgesichert — 2026-09-30)

- **`GET /api/simulation/<id>/actions` liefert `SimActionPage` (`items`/`next_cursor`):** Die früheren Felder `offset`, `count` und `actions` entfallen zugunsten des Cursor-Schemas. `SimActionRecord`, `SimActionPage` und `RoundSummary` sind Pydantic-v2-Verträge (`extra="forbid"`) in `backend/app/contracts/sim_action_contract.py`; JSON-Schemas unter `schemas/`.
- **`action_type`-Filter validiert:** Ein unbekannter `action_type`-Query-Wert antwortet mit 400 `validation_failed` statt einer stillen Leerliste.
- **`GET /api/simulation/<id>/rounds` 500-Schutz:** Altbestand mit unbekanntem `platform`-Wert wird in `get_simulation_rounds` und `_agent_action_to_record` übersprungen (`logger.warning`), nicht als 500 geworfen — analog zur `evidence_omitted`-Degradations-Haltung.
- **PostCreatedEvent v2:** `PostCreatedEvent` (`backend/app/contracts/post_event_contract.py`) trägt `in_reply_to_post_id`, `quoted_post_id` und eine persistente `post_id`.
- Regressionstests: `test_unknown_platform_skipped_without_500`, `test_invalid_action_type_returns_400`, `test_valid_action_type_does_not_return_400`. (#1713)
