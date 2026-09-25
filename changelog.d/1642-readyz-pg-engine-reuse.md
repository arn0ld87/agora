## Fixed

- `/readyz` baut für die PostgreSQL-Probe nicht mehr bei jedem Aufruf eine neue
  SQLAlchemy-Engine (#1642). Mit aktivem `AGORA_*_BACKEND=postgres` stand dadurch
  alle 30 s — im Takt des Docker-Healthchecks — `PostgreSQL engine initialised
  (pool=no)` im Log. Die Probe-`Database` wird jetzt pro Prozess einmal gebaut und
  nur bei geänderter `DATABASE_URL` ersetzt; NullPool und das kurze
  Verbindungs-Timeout bleiben, jede Probe öffnet weiterhin eine frische Verbindung.
