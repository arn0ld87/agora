# Slice 7 (Repo-Review-Folge, F1): Deployment-Doku Dev + Prod-Like

**Datum:** 2026-05-01
**Branch:** `claude/brave-haslett-a7e4e8` (Worktree)
**Bezug:** [`docu/2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md), Sub-Slice F1.

## Ziel

Den im Repo-Review als „fehlende Doku" markierten Punkt #1 schliessen: zwei
Markdown-Dateien als Single-Source-of-Truth fuer Setup-Pfade. README so
verlinken, dass Leser die Deployment-Anleitung ohne Suche erreichen.

## Ausgangslage

- F1-Scope laut Plan:
  - `docu/deployment-dev.md`: Lokaler Dev-Betrieb (Vite + Flask, ohne
    Docker), Compose-Dev-Pfad (`target: dev`, Loopback-Ports,
    Hot-Reload), Voraussetzungen (`uv`, `pnpm`/`npm`, Neo4j, Redis
    optional), Verweis auf `auth.md`.
  - `docu/deployment-prod-like.md`: Gunicorn (`--workers 2`),
    Reverse-Proxy (Traefik/Nginx), Tailscale/WireGuard, CORS-/Auth-Konfig
    (kein `AGORA_CORS_ALLOW_ALL`), Compose-Prod-Override (Frontend-Port
    nicht veroeffentlicht), Neo4j ohne Host-Port, Verweis auf
    `dependency-risk-register.md`.
- Akzeptanzkriterium: README verlinkt beide Dokumente; `npm run check` gruen.
- Bestand: `docker-compose.yml` (Dev-Default `target: dev`,
  127.0.0.1-Bindings), `docker-compose.prod.yml` (`target: prod`, `!override`
  fuer Backend-Port, `!reset []` fuer Neo4j-Ports), Multi-Stage-Dockerfile
  (Stages `base`, `dev`, `prod-builder`, `prod` mit Gunicorn-CMD).

## Vorgehen

1. Plan + bestehende Doku gelesen ([`auth.md`](auth.md),
   [`security-hardening.md`](security-hardening.md),
   [`dependency-risk-register.md`](dependency-risk-register.md)),
   Compose-Files und Dockerfile geprueft, damit die Deployment-Doku den
   tatsaechlichen Code-Stand widerspiegelt und nicht parallel daneben lebt.
2. `docu/deployment-dev.md` geschrieben:
   - Voraussetzungen (Node 18+, Python 3.11+, `uv`, Neo4j 5.18+, Ollama,
     optional Docker und Redis).
   - **Pfad A — Bare-Metal**: `npm run setup:all` + `npm run dev`,
     `.env`-Minimalkonfiguration, lokales Neo4j entweder als System-Service
     oder via `docker compose up -d neo4j redis`, `npm run check` als Gate.
   - **Pfad B — Docker Compose `target: dev`**: Endpoint-Tabelle
     (Frontend 5173, Backend 5001, Neo4j 7474/7687, Redis intern), Volume-
     und tmpfs-Layout, haeufige Dev-Kommandos (Recreate, Rebuild,
     Volume-Reset), Read-Only-Rootfs-Hinweis.
   - **Auth-Token im Dev-Modus**: kurzer Token-Setup-Block, Verweis auf
     [`auth.md`](auth.md).
   - **Stolperfallen**: fehlendes `NEO4J_PASSWORD`, Embedding-Mismatch
     (`EMBEDDING_MODEL` ↔ `VECTOR_DIM`), `host.docker.internal`,
     Vite-Port-Belegung, Read-Only-Rootfs-EROFS.
3. `docu/deployment-prod-like.md` geschrieben:
   - Disclaimer: kein echtes Multi-User-AuthN, Single-User-Vertrauensmodell
     bleibt.
   - **Compose-Prod-Pfad**: Begruendung der drei Override-Punkte
     (`target: prod`, `agora.ports: !override`, `neo4j.ports: !reset []`),
     Start-Command, Compose-2.24+-Hinweis fuer `!reset`.
   - **Gunicorn**: `--workers 2`, Begruendung warum Bind im Container
     `0.0.0.0:5001` ok ist (Read-Only, Loopback-Host-Port), Multi-Worker-
     Konsequenz fuer Single-Use-Tickets (Redis Pflicht).
   - **Reverse-Proxy**: Traefik-Beispiel (Tailscale-Hostname, ACME),
     Nginx-Skizze inkl. `client_max_body_size 60m`, `proxy_buffering off`
     fuer SSE.
   - **Tailscale / WireGuard**: Funnel-Hinweis (Internet-exposed, Audit
     pflicht), `tailscale serve --bg` als Default,
     `AGORA_EXTRA_ORIGINS`-Beispiel.
   - **CORS / Auth**: Pflicht-Env (`FLASK_DEBUG=false`, `SECRET_KEY`,
     `NEO4J_PASSWORD`, `AGORA_AUTH_TOKEN`); explizite Negativ-Liste
     (`AGORA_CORS_ALLOW_ALL`, `AGORA_ALLOW_ANONYMOUS`, `FLASK_DEBUG=true`,
     `FLASK_HOST=0.0.0.0`); Memory-Mode-Empfehlung fuer Frontend-Token.
   - **Neo4j**: Browser nur via `cypher-shell` oder SSH-Forward, Memory-
     Settings im Compose verankert.
   - **Ollama**: Host-only Default, `host-gateway`-Bridge, GPU-Status via
     `/api/status`.
   - **Update- + Rollback-Pfad**: `docker compose build` + `up -d --no-deps
     --force-recreate`, Image-SHA-Pin als Rollback.
   - Verweise auf [`deployment-dev.md`](deployment-dev.md), [`auth.md`](auth.md),
     [`security-hardening.md`](security-hardening.md),
     [`dependency-risk-register.md`](dependency-risk-register.md),
     [`SECURITY_REVIEW_SUMMARY.md`](SECURITY_REVIEW_SUMMARY.md).
4. `README.md` an drei Stellen ergaenzt:
   - **DE Schnellstart-Header (`### Schnellstart`)**: Hinweisblock mit Links
     auf beide Deployment-Files.
   - **EN Quick-Start-Header (`### Quick Start`)**: spiegelnder Hinweis.
   - **DE und EN Doku-Indizes** (am Ende der `Entwicklung`- bzw.
     `Development checks`-Bloecke): bestehende Mini-Liste durch
     vollwertigen Doku-Index ersetzt (Deployment, Auth & Security,
     API-Contracts, Architektur).
5. `CHANGELOG.md` `[Unreleased]` um neue `### Docs`-Sektion erweitert
   (Slice-7-Block) — Konvention aus den Slice-1- bis Slice-6-Eintraegen
   uebernommen (Datei-Pfade verlinkt, Verweis aufs Arbeitsprotokoll).
6. Dieses Arbeitsprotokoll geschrieben.
7. `npm run check` als Gate ausfuehren, danach commit + PR + Merge.

## Geaenderte / neue Dateien

| Datei | Aktion | LOC ca. |
|---|---|---|
| `docu/deployment-dev.md` | neu | 180 |
| `docu/deployment-prod-like.md` | neu | 245 |
| `README.md` | edit (3 Stellen) | +20 / -5 |
| `CHANGELOG.md` | edit (`[Unreleased]` → neuer `### Docs`-Block) | +4 |
| `docu/2026-05-01-slice-7-deployment-doku-arbeitsprotokoll.md` | neu | dieses File |

## Verifikation

- `npm run check` (Backend-Lint, Backend-Tests, Frontend-Lint, Frontend-Tests,
  Frontend-Build) — Doku-Slice darf den Gate nicht roetlich faerben. Der
  Slice fasst keine Code-Pfade an; gruen heisst Bestand stabil.
- README-Verlinkungen sichtgepruefte Anchor (`./docu/deployment-dev.md` und
  `./docu/deployment-prod-like.md`) — Markdown-Render in GitHub funktioniert,
  Pfade relativ.
- Inhalts-Konsistenz mit Code: Compose-Targets, Bind-Adressen, Port-Werte,
  Env-Pflichtwerte, Gunicorn-CMD und `!override`/`!reset`-Mechanik wurden
  gegen `docker-compose.yml`, `docker-compose.prod.yml`, `Dockerfile`,
  `backend/app/__init__.py` und `backend/app/utils/auth.py` abgeglichen.

## Akzeptanzkriterien (laut Plan)

- [x] `docu/deployment-dev.md` existiert und deckt Bare-Metal + Compose-Dev
      ab; verweist auf `auth.md`.
- [x] `docu/deployment-prod-like.md` existiert und deckt Gunicorn,
      Reverse-Proxy, Tailscale/WireGuard, CORS/Auth-Hardrejects,
      Compose-Prod-Override (Frontend-Port entfaellt), Neo4j ohne
      Host-Port; verweist auf `dependency-risk-register.md`.
- [x] README verlinkt beide Dokumente (DE + EN, je Schnellstart-Header und
      Doku-Index).
- [ ] `npm run check` gruen — pending bis zum tatsaechlichen Lauf.

## Issue / Milestone

- F1 ist Teil des Folge-Plans, kein offenes GitHub-Issue mit
  `Closes #N`-Bezug.
- Milestone-Counter: kein Milestone direkt zugeordnet — Repo-Review-Folge
  laeuft als Doku-Sweep.

## Followups

- F2 — Security-Threat-Model.
- F3 — Operations + Backup/Restore.
- F4 — Release-Process.
- F5 — Test-Coverage-Luecken (SSRF, Upload-Limits, Cypher-Sanitizer).
- F6 — Branch-Cleanup + README-Update.
