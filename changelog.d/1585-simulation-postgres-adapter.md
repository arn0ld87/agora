### Added

- **Simulationsmetadaten: PostgreSQL-Adapter und Datenmigration** — `PostgresSimulationRepository` auf der neuen Tabelle `agora.simulations` (Alembic-Revision `c4e8a1d93b56`, Fremdschlüssel `project_id → agora.projects`), Schalter `AGORA_SIMULATION_BACKEND=file|postgres` (Default `file`; `postgres` verlangt `AGORA_PROJECT_BACKEND=postgres` und `DATABASE_URL`), Migrationsskript `backend/scripts/migrate_simulations_to_postgres.py` mit `--dry-run`/`--verify` und Runbook `docs/runbooks/simulation-postgres-umstellung.md`. Umgeschaltet ist nichts. (#1585)
