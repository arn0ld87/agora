### Added

- **Gesamt-Migrations- und Rollback-Gate** — `backend/tests/integration/test_metadata_migration_rollback.py` migriert einen Legacy-Bestand aller fünf Metadaten-Domänen (LLM-Profil, Projekt, Simulation, Run, Report) mit den `migrate_*_to_postgres.py`-Skripten, verlangt Exit 0 von jedem `--verify`, startet die App mit allen Schaltern auf `postgres` (Legacy-Metadateien versteckt), schaltet zurück auf Legacy und verlangt identische Antworten der Profil-, Projekt-, Simulations-, Run- und Report-Endpunkte ohne Datenverlust. Läuft im CI-Integration-Job gegen PostgreSQL (Plan §36). (#1589)
