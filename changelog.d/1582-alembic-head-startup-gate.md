### Added

- **Startabbruch bei Alembic-Drift** — `create_app` prüft ab sofort, sobald irgendeine Ablage auf `AGORA_*_BACKEND=postgres` steht, ob die Revision in der Datenbank dem Alembic-Head aus `backend/migrations/` entspricht (`app/infrastructure/postgres/schema_gate.py::verify_schema_at_head`). Fehlt `alembic upgrade head`, mehrere Alembic-Heads oder eine leere Versionstabelle brechen den Start mit einer Meldung ab, die beide Revisionen nennt — ohne URL oder Passwort. Legacy-Defaults bauen dabei weiterhin keine Verbindung auf. (#1582)
