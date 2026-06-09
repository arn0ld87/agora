# Dev-Stack: Docker-Compose-Port-Fix + Build-Context-Hygiene

**Datum:** 2026-05-04  
**Typ:** Arbeitsprotokoll / Repo-Hinweis für Commit- und PR-Kontext  
**Scope:** lokaler Dev-Stack (`docker compose up -d --build agora`)

## Ausgangslage

Beim lokalen Start des Dev-Stacks schlug `docker compose up -d --build agora` reproduzierbar mit folgendem Fehler fehl:

```text
failed to bind host port 127.0.0.1:5173/tcp: address already in use
```

Zusätzlich fiel auf, dass der Docker-Build-Context unnötig groß war:

- vorher beobachtet: **~1.14 GB** Build-Context

Das machte Dev-Rebuilds langsam und unnötig teuer.

## Root Cause

### 1) Port-Konflikt nicht durch Fremdprozess, sondern durch Compose-Merge

Der Konflikt kam aus der kombinierten Compose-Konfiguration selbst:

- `docker-compose.yml` publizierte bereits `127.0.0.1:5173:5173`
- `docker-compose.override.yml` publizierte **zusätzlich** nochmal `5173:5173`

Durch den Compose-Merge bekam der Service `agora` damit **zwei Port-Bindings** für denselben Frontend-Port. Der Fehler war also kein externer Listener, sondern ein doppeltes Port-Mapping im finalen Compose-Resultat.

### 2) Build-Context durch nicht benötigte Artefakte aufgebläht

Der größte Treiber war vor allem:

- `backend/.cache` ≈ **1.1 GB**

Zusätzlich wurden diverse Repo-Artefakte mit in den Build-Context geschickt, obwohl sie für den Container-Build nicht benötigt werden (Doku, Design-Artefakte, lokale Agent-/Editor-Verzeichnisse etc.).

## Änderungen

### A. `docker-compose.override.yml`

Der redundante `ports:`-Block wurde entfernt.

**Ziel:**
- kein doppeltes Publish von Port 5173 mehr
- Override bleibt auf Dev-spezifische Bind-Mounts fokussiert
- Loopback-Bind aus `docker-compose.yml` bleibt die Single Source of Truth

### B. `.dockerignore`

Die Ignore-Liste wurde erweitert um lokal irrelevante Build-Kontext-Brocken, u. a.:

- `backend/.cache`
- `backend/.pytest_cache`
- `.git`
- `.pi`
- `.playwright-mcp`
- `.cursor`
- `.serena`
- `.claude`
- `docu`
- `design`
- `media`
- `PR.pdf`
- mehrere Plan-/Artefakt-Dateien

## Verifikation

### Compose-Konfiguration

`docker compose config` zeigte nach dem Fix für `agora` nur noch die erwarteten Host-Port-Bindings:

- `127.0.0.1:5173 -> 5173/tcp`
- `127.0.0.1:5001 -> 5001/tcp`

### Container-Start

Erfolgreich verifiziert mit:

```bash
docker compose up -d agora
```

Danach liefen die relevanten Container wieder sauber:

- `agora`
- `agora-redis`
- `agora-neo4j`

### Build-Context

Vorher:

- **1.14 GB**

Nach `.dockerignore`-Bereinigung:

- **25.56 kB**

Damit ist der Build-Context praktisch auf die tatsächlich für den Image-Build benötigten Dateien geschrumpft.

## Wirkung

### Funktional

- `docker compose up -d --build agora` scheitert nicht mehr am Frontend-Port 5173
- der Dev-Container startet wieder konsistent

### Operativ

- deutlich schnellere Docker-Builds im Dev-Workflow
- weniger unnötiger Dateitransfer zum Docker-Daemon
- geringere Wahrscheinlichkeit, dass lokale Caches/Artefakte versehentlich in den Build geraten

## Betroffene Dateien

- `docker-compose.override.yml`
- `.dockerignore`

## Empfehlung für Commit-/PR-/GitHub-Kontext

Wenn die Änderung in Commit, PR oder Release-Notizen erwähnt wird, sollte der Kern so zusammengefasst werden:

> Fixes a dev-compose port collision caused by duplicate 5173 publishing in `docker-compose.override.yml` and drastically reduces Docker build context by excluding local caches and non-runtime project artifacts via `.dockerignore`.

Kurz auf Deutsch:

> Behebt einen Dev-Compose-Portkonflikt durch doppeltes 5173-Port-Mapping im Override und reduziert den Docker-Build-Context drastisch durch bereinigte `.dockerignore`-Regeln.

## Follow-up

Optional später sinnvoll:

1. prüfen, ob weitere Build-Artefakte gezielter statt per `COPY . .` kopiert werden können
2. Dev-/Prod-Docker-Workflows in `docu/deployment-dev.md` bzw. README explizit um den Hinweis ergänzen, dass `docker-compose.override.yml` **keine Ports** definieren soll, solange das Basis-Compose bereits bindet
3. bei Bedarf Changelog-Eintrag unter `Unreleased > Changed` oder `Fixed` ergänzen
