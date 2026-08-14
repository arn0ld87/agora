### Fixed (nginx-Sidecar — 2026-08-13)

- **502 nach Backend-Container-Neubau behoben:** `deploy/nginx/agora.conf` nutzte
  literale `proxy_pass http://agora:5001;`-Direktiven. nginx löst einen literalen
  Upstream-Hostnamen genau einmal beim Config-Load auf und cacht die IP für die
  gesamte Prozesslebensdauer. Wurde der `agora`-Container neu erzeugt, bekam er
  per Docker-DHCP eine andere IP; nginx proxyte weiter auf die alte. Im
  beobachteten Fall war die freigewordene IP inzwischen an `agora-redis` vergeben
  — jeder `/api/`-Request endete in `connect() failed (111: Connection refused)`
  gegen den Redis-Port und damit in einem 502. Ein `nginx -s reload` heilte es nur
  bis zum nächsten Container-Neubau. Jetzt lösen Docker-Resolver `127.0.0.11`
  (`valid=10s`) und ein Variablen-`proxy_pass` den Upstream zur Laufzeit auf.
  Regressionstest: `backend/tests/test_nginx_upstream_resolution.py`.
