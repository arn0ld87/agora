### Added

- **Report-Metadaten: PostgreSQL-Adapter und Datenmigration** — `PostgresReportRepository` auf der neuen Tabelle `agora.reports` (Alembic-Revision `8d6e0b3c2f15`, linear auf `3f9b2d7e6a41`; Primärschlüssel ist der Ablageschlüssel, `payload jsonb` hält den vollständigen Inhalt von `meta.json`; Fremdschlüssel `simulation_id → agora.simulations`, nullable, `ON DELETE SET NULL`), Schalter `AGORA_REPORT_BACKEND=file|postgres` (Default `file`; `postgres` verlangt `AGORA_SIMULATION_BACKEND=postgres` und `DATABASE_URL`), Migrationsskript `backend/scripts/migrate_reports_to_postgres.py` mit `--dry-run`/`--verify` und Runbook `docs/runbooks/report-postgres-umstellung.md`. Report-Inhalte bleiben Dateien. Umgeschaltet ist nichts. (#1588)

### Changed

- **Report löschen über den Port** — `ReportRepository` hat `delete()`; `ReportManager.delete_report` entfernt den Metadatensatz über das Repository und danach die Inhalte. Mit `AGORA_REPORT_BACKEND=postgres` bliebe sonst die Zeile stehen. (#1588)
