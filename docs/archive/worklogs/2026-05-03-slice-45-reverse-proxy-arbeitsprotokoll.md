# Sub-Slice 45 — F1.1 Reverse-Proxy-Sidecar (M9 #2) — Arbeitsprotokoll

**Datum:** 2026-05-03
**Branch:** `feat/layer-9-slice-45-reverse-proxy`
**Closes:** #106

---

## Ziel

Einen lauffähigen nginx-Sidecar als Compose-Override bereitstellen, der das statische
Frontend-Bundle ausliefert und API-Calls an den agora-Container durchreicht —
damit ist der in `docker-compose.prod.yml` vorausgesetzte Reverse-Proxy im Repo
verankert (PLAN.md F1).

---

## Befund vor dem Slice

1. `docker-compose.prod.yml` setzt einen externen Reverse-Proxy voraus (Backend
   bindet auf `127.0.0.1:5001`, Vite-Port entfällt), liefert aber keinen mit.
2. Issue #106 trackt das seit dem Prod-Hardening-Slice: „Reverse-Proxy vor
   Prod-Container für statisches Frontend". Früherer Workaround: Operatoren
   bauten ihre nginx-Konfig selbst nach der Skizze in `deployment-prod.md`.
3. Die Nginx-Skizze in `deployment-prod.md` (Zeile 148–175) enthielt keinen
   SSE-tauglichen `/api/simulation/`-Block und kein eigenes `healthz`-Endpoint.
   Sie war als Orientierungshilfe gemeint, nicht als Drop-In-Konfig.

---

## Geänderte Dateien

| Datei | Aktion | Begründung |
|---|---|---|
| `deploy/nginx/agora.conf` | neu | nginx Server-Block mit SSE-Routes, gzip, healthz-Endpoint |
| `deploy/compose/docker-compose.prod-with-proxy.yml` | neu | Compose-Override für nginx-Sidecar, `!reset []` auf agora-Ports |
| `scripts/verify-deploy.sh` | erweitert | Proxy-Auto-Detect, neue Probes gegen :80/healthz, /health, / |
| `docs/deployment-prod.md` | erweitert | Drei Topologie-Sections + Verifikations-Bullets |
| `.github/workflows/docker-image.yml` | erweitert | Neuer Job `prod-proxy-smoke` |
| `CHANGELOG.md` | erweitert | `[Unreleased]/Build`-Eintrag Sub-Slice 45 |
| `docs/2026-05-03-slice-45-reverse-proxy-arbeitsprotokoll.md` | neu | dieses Dokument |

---

## Architektur-Entscheidungen

### Sidecar statt eingebautem Reverse-Proxy im agora-Image

nginx läuft als eigener Container (`agora-nginx`) im selben Compose-Netzwerk.
Vorteile: unabhängiger Restart, separate Logs, kein nginx im agora-Image nötig.
Nachteil: ein zweiter Container. Dieser Trade-off ist bei Prod-Setups üblich und
akzeptabel.

### Bind-Mount für `frontend/dist` statt Multi-Stage-Copy in ein nginx-Image

Der Operator entscheidet, welches Frontend-Bundle er deployt. Ein eigenes
nginx-Image würde das Bundle einfrieren — der Operator müsste bei jedem
Frontend-Update ein neues Image bauen. Bind-Mount auf `./frontend/dist` ist
operativ einfacher: `npm run build` lokal laufen lassen, Stack neu starten.
Caveat ist explizit dokumentiert.

### Drei dokumentierte Topologien

Das Repo liefert eine Default-Implementierung (Sidecar-Nginx), dokumentiert aber
zwei Alternativen (Traefik-Labels, Tailscale-Funnel) für Stacks, die
bereits eine andere Proxy-Infrastruktur betreiben. Keine dieser Alternativen
erfordert eigene Repo-Dateien — die Doku reicht.

### SSE-Route vor API-Route

nginx verwendet Longest-Prefix-Match. `location /api/simulation/` muss vor
`location /api/` in der Konfig stehen, damit der SSE-Block greift. Das ist im
`agora.conf` kommentiert.

---

## Akzeptanz-Checks

- [ ] `docker run --rm -v "$(pwd)/deploy/nginx/agora.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t` gibt `syntax is ok` / `test is successful`
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f deploy/compose/docker-compose.prod-with-proxy.yml config > /dev/null` ohne Fehler
- [ ] `bash -n scripts/verify-deploy.sh && echo OK` gibt `OK`
- [ ] `python3 -c "import yaml, sys; yaml.safe_load(open('.github/workflows/docker-image.yml'))"` gibt kein Error
- [ ] Backend-Tests: `cd backend && uv run pytest -x -q` — keine Regression
- [ ] `git diff --exit-code schemas/` — keine Schema-Drift (keine Contracts angefasst)

---

## Folge-Slices

- **Sub-Slice 46–47 (F2 Auth-Hardening):** VITE_AGORA_TOKEN per Build-ARG gaten
  statt im Bundle landen; `?token=`-URL-Parameter in Prod hart deaktivieren.
  Das ist der offene PLAN.md-F2-Block.
- **Sub-Slice 48 (F3 Gunicorn-Gevent):** `-k gevent` statt sync-Worker mit
  `--timeout 600`. Voraussetzung: gevent-Monkey-Patching vs. OASIS-Subprozess
  per Smoke verifizieren (siehe `docs/2026-04-29-prod-slice2-gunicorn.md`).

---

## Caveats

- **HTTPS-Termination** muss extern erfolgen (Tailscale-Funnel, Cloudflare-Tunnel,
  separater nginx mit Let's Encrypt auf Port 443). Dieser Slice liefert nur HTTP/:80.

- **`frontend/dist` muss vom Operator gebaut werden** bevor der Sidecar startet.
  Ohne lokales Build zeigt nginx die nginx-Default-Welcome-Page statt der
  Agora-SPA. Die CI handhabt das im `prod-proxy-smoke`-Job mit `npm run build`.
  Lokale Operatoren müssen das explizit wissen — steht in
  `docs/deployment-prod.md` (Sidecar-Nginx-Caveats).

- **VITE_AGORA_TOKEN-Bundle-Problem (PLAN.md F2.1) bleibt ungelöst.** Der Token
  landet weiter im Frontend-Bundle zur Build-Zeit. Der Proxy selbst löst das
  Auth-Problem nicht — er reicht den Authorization-Header durch. Die Lösung
  erfordert einen Login-Endpoint oder Build-ARG-Gating (Sub-Slice 46–47).
