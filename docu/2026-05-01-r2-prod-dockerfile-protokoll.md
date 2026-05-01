# R2 — Prod-Dockerfile-Target · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** R2

## Implementierung

Multi-Stage `Dockerfile`:

- `base` — gemeinsame Layers (Python 3.11, Node, uv, agora-User, /app-Ownership)
- `dev` — bisheriger Default; `npm ci` + `uv sync` + Bind-Mount + `npm run dev`. CMD bleibt `npm run dev`, exposed Ports 5173+5001.
- `prod-builder` — baut nur das Frontend-Bundle (`vite build`).
- `prod` — schlanke Runtime: `uv sync --no-dev`, `gunicorn` extra installiert. Kein npm/Vite zur Laufzeit. Kopiert `frontend/dist` aus `prod-builder`. CMD ruft `gunicorn` vor Flask (`app:create_app()`), 2 Worker, port 5001.

Neue Datei `docker-compose.prod.yml` (Override):

- `target: prod` zwingt den prod-Stage
- Nur Backend-Port wird publiziert (Vite läuft nicht mehr)
- Bind-Mount für Sources entfällt; Reverse-Proxy davor empfohlen

## Verwendung

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`docker compose ... config --quiet` validiert den Override.

## Hinweise

Statisches Frontend wird im Prod-Setup nicht von Flask serviert — das soll bewusst über einen Reverse-Proxy (nginx/Traefik) laufen. Wer eine all-in-one Variante braucht, ergänzt einen Static-Mount in `app/__init__.py` oder einen sidecar-nginx-Container.

`npm run check` grün, kein lokaler Lint-Drift.
