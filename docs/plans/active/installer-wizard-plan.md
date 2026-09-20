# Installer-Wizard: grafisches Onboarding für Host-Deployment

> Status: Entwurf, ungebrancht. Nicht verwechseln mit dem bereits existierenden
> In-App-Onboarding (`backend/app/api/onboarding.py`, `frontend/src/views/onboarding/`),
> das Profil/LLM-Provider-Setup **nach** dem ersten Start abdeckt. Dieses Feature
> liegt zeitlich **davor**: Container-Bring-up auf einem frischen Host.

## Ziel

`./install.sh --wizard` startet einen lokal gebundenen Webserver mit einer
Vue-SPA, die durch Voraussetzungs-Check → Secrets/Provider-Wahl →
Container-Deploy (Live-Log) → Übergabe an die echte Agora-Instanz führt.
Zielhost: generischer frischer Host, kein Multi-Tenant-Sonderfall wie armserver.

## Warum kein Erweitern des bestehenden `onboarding_bp`

Der bestehende Onboarding-Flow läuft **innerhalb** der laufenden Flask-App
(braucht Neo4j/Redis/DB bereits erreichbar). Der Wizard muss **vor**
`docker compose up` funktionieren — auf einem Host ohne bun/uv/laufende
Container. Deshalb ein eigenständiger, minimaler Prozess, kein Blueprint der
Hauptanwendung.

## Architektur

```
install.sh --wizard
  └─ startet backend/installer/server.py (Flask, 127.0.0.1 only, Ein-Token-Auth)
       ├─ serviert backend/installer/static/  (vorgebaute Vue-SPA, kein Build zur Laufzeit nötig)
       ├─ GET  /api/installer/preflight   → Docker/Compose-Version, Ports frei?, Diskspace, OS
       ├─ POST /api/installer/config      → schreibt .env (SECRET_KEY/AGORA_AUTH_TOKEN/
       │                                     AGORA_SECRET_KEY/AGORA_FERNET_KEY über
       │                                     scripts/lib/env-secrets.sh — dieselbe Logik
       │                                     wie install.sh, keine zweite Heuristik)
       ├─ POST /api/installer/deploy      → startet `docker compose up -d` als Subprozess
       ├─ GET  /api/installer/deploy/stream (SSE) → Live-Zeilen pro Service
       └─ GET  /api/installer/health      → Healthcheck-Polling bis alle Container "healthy"
  └─ öffnet Browser auf http://127.0.0.1:<port>/setup?token=<einmalig>
  └─ wartet auf Fertig-Signal, danach normaler --docker-Ablauf mit dem geschriebenen .env
```

### Sicherheitsanker

- Server bindet ausschließlich `127.0.0.1`, kein `0.0.0.0`.
- Einmal-Token in der URL, ungültig nach `complete`-Signal oder Prozessende.
- Secrets nie im Klartext geloggt; API-Keys nur einmal zum Schreiben ins `.env`
  übertragen, nie zurückgegeben (Metadaten-Regel aus AGENTS.md gilt auch hier).
- `scripts/lib/env-secrets.sh` wird aus `install.sh` **extrahiert** (aktuell
  `ensure_secret`-Funktionen dort inline), damit Wizard und CLI-Pfad exakt
  dieselbe Secret-Erzeugung nutzen — keine zweite Implementierung.
- Vor dem Schreiben ins `.env`: Warnhinweis-Schritt im Wizard (Pflicht laut
  `05-sicherheit-und-verbote.md`: „erst warnen, dann handeln").

### Frontend

Eigenständiges, kleines Vite/Vue-Projekt `installer-ui/` (NICHT Teil von
`frontend/`, da dessen Build bereits eine laufende Toolchain voraussetzt, die
auf einem frischen Host evtl. noch fehlt). Prebuilt-Dist wird committed unter
`backend/installer/static/`. Schritte: Willkommen → Preflight (Live-✓/✗) →
Secrets & Provider → Deploy (Fortschritt je Service, Log-Tail) → Fertig (Link
zur echten Agora-Instanz, wo das bestehende In-App-Onboarding weiterläuft).

## Slices

1. **Lead (dieser Chat, Cross-Layer/Secrets-Trigger)**: `scripts/lib/env-secrets.sh`
   extrahieren, `install.sh` darauf umstellen (Regressionstest: bestehendes
   `--docker`-Verhalten unverändert), `backend/installer/` Skeleton
   (Flask-Server, Preflight, SSE-Deploy-Runner, Token-Auth).
2. **agora-frontend-worker-m3**: `installer-ui/` SPA nach Spec unten bauen,
   Prebuilt-Dist nach `backend/installer/static/` exportieren.
3. **agora-doc-worker-m3**: README-Abschnitt „Grafischer Installer",
   `docs/STATUS.md`, Changelog-Fragment, `docs/runbooks/installer-wizard.md`.
4. **Lead**: `install.sh --wizard`-Flag verdrahten, End-to-End-Test in
   isolierter Umgebung (nicht auf armservers Live-Stack — dort laufen bereits
   `agora`, `agora-neo4j`, `agora-redis`, `agora-nginx` produktiv).

Max. zwei schreibende Worker gleichzeitig (Repo-Regel) — Slice 2 und 3 können
parallel laufen, Slice 1 und 4 bleiben beim Lead.

## Out of Scope

- Multi-Tenant-Hosts wie armserver (Portkollisionen, Traefik-Routing) — eigenes
  Follow-up, nutzt dann `deploy-meinserver.sh` als Vorlage statt `install.sh`.
- Kein Ersatz für das bestehende In-App-Onboarding (Profil/LLM) — reiner
  Übergabepunkt.
