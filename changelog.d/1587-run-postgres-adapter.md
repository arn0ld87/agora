### Added

- **Run-Registry: PostgreSQL-Adapter und Datenmigration** — `PostgresRunRepository` auf der neuen Tabelle `agora.runs` (Alembic-Revision `3f9b2d7e6a41`, linear auf `c4e8a1d93b56`; `payload jsonb` hält das vollständige Manifest, Spalten sind Projektionen; Fremdschlüssel `simulation_id → agora.simulations`, nullable, `ON DELETE SET NULL`), Schalter `AGORA_RUN_BACKEND=file|postgres` (Default `file`; `postgres` verlangt `AGORA_SIMULATION_BACKEND=postgres` und `DATABASE_URL`), Migrationsskript `backend/scripts/migrate_runs_to_postgres.py` mit `--dry-run`/`--verify` und Runbook `docs/runbooks/run-postgres-umstellung.md`. Lease/Heartbeat bleiben im Manifest. Umgeschaltet ist nichts. (#1587)

### Changed

- **PostgreSQL-Prozess-Adapter mit Verbindungs-Timeout** — `get_database()` baut die Engine mit `connect_timeout=10`, weil die Start-Reconciliation mit `AGORA_RUN_BACKEND=postgres` die Registry aus der Datenbank liest. (#1587)
