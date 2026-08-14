### Changed (Persona-Floor 50 → 20 — 2026-08-12)

- **`MIN_PERSONA_TABLE_ROWS` von 50 auf 20 gesenkt:** praktische Läufe mit kleineren DACH-Seed-Dokumenten erreichen nach typbasierter Vorfilterung, Dedup und LLM-seitiger Eignungsprüfung häufig nur ~40 elige Personas und scheiterten am harten 50er-Report-Gate (`Persona-Mindestanzahl nicht erreicht: 42/50`), obwohl der Report inhaltlich erstellbar war. 20 hält eine statistisch noch belastbare Untergrenze für die Persona-Tabelle, lässt dokumenttreue Runs aber durch.

### Fixed (nginx-Sidecar — 2026-08-13)

- **502 nach Backend-Container-Neubau behoben:** `deploy/nginx/agora.conf` nutzte literale `proxy_pass http://agora:5001;`-Direktiven, nginx cachte die IP prozesslebenslang. Jetzt: Docker-Resolver `127.0.0.11` (`valid=10s`) + Variablen-`proxy_pass` löst den Upstream pro Request auf. Regressionstest: `backend/tests/test_nginx_upstream_resolution.py`.

### Fixed (install.sh — 2026-08-13)

- **`ensure_secret` robuster:** Fehlende Keys werden angehängt statt still übersprungen; fail-fast wenn der Key danach nicht in `.env` steht. Regressionstest: `backend/tests/test_install_ensure_secret.py`.
