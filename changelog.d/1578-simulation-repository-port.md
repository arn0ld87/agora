### Changed (Simulationsmetadaten: Vertrag und Repository-Port — 2026-09-24)

- **`SimulationManager` delegiert Metadatenzugriffe jetzt an `SimulationRepository`:** `state.json`-Lesen und -Schreiben laufen über den neuen Port `app/repositories/simulation_repository.py` und den Dateiadapter `app/services/file_simulation_store.py`. Vertrag: `app/contracts/simulation_record_contract.py` (`SimulationRecord`, Pydantic v2). Kein Verhalten geändert, kein Datenverlust — `SimulationState.to_dict()` → `SimulationRecord` → zurück ist verlustfrei verifiziert. PostgreSQL-Adapter folgt in #1585. (#1578)
