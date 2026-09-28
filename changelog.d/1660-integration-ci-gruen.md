### Fixed

- CI-Job `integration` auf `main` war rot (#1660), aus zwei Gründen. Erstens
  brachte das Runner-Image `pg_dump` 16 mit, der Service läuft aber auf
  PostgreSQL 17; `pg_dump` bricht bei neuerer Server-Hauptversion mit
  `server version mismatch` ab, und alle sechs Backup/Restore-Integrationstests
  scheiterten daran. Der Job installiert jetzt `postgresql-client-17` aus dem
  PGDG-Repository und stellt ihn vor das Runner-`pg_dump`. Zweitens meldeten sich
  zwei Startup-Tests über `create_app()` mit einem Dummy-Passwort am echten
  Neo4j-Service an; nach drei Fehlversuchen sperrte Neo4j per
  `AuthenticationRateLimit`, und der nächste echte Neo4j-Test scheiterte. Diese
  Tests ersetzen `Neo4jStorage` jetzt durch einen Stub. Zwei Regressionstests im
  PR-Gate (`tests/contracts/test_ci_integration_env.py`) prüfen beides.
