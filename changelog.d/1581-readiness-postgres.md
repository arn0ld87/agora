### Added

- **Readiness: `/readyz` meldet PostgreSQL-Zustand** — neuer Check `postgres` mit maschinenlesbarem `state` (`ok`/`unavailable`/`disabled`). Solange kein `AGORA_*_BACKEND` auf `postgres` steht, bleibt der Check `disabled` und baut keine Verbindung auf; erst dann probt er `SELECT 1` über einen kurzlebigen `Database`-Adapter mit kleinem Verbindungs-Timeout. Fehlerdetails im Response-Body sind generisch — nie Host, User, Passwort, Port oder Datenbankname aus `DATABASE_URL`. (#1581)
