# Plan: Vereinfachte Paket-basierte Installation

Status: Entwurf · 2026-04-28

## 1. Ausgangslage

Der aktuelle "einfache" Pfad ist `docker compose up -d`. Damit werden bei jedem
Setup drei Dinge gemacht, die Zeit, Disk und Bandbreite kosten:

- Das **Agora-Image wird lokal gebaut** (`Dockerfile`): Python 3.11 Basis,
  `apt-get nodejs npm curl`, `uv` aus dem `ghcr.io/astral-sh/uv`-Image kopieren,
  dann `npm ci` (root + frontend) und `uv sync`. Bei jedem Dependency-Bump
  wieder.
- **Neo4j 5.18-community** wird als separater Container gezogen (~600 MB) und
  in eigenem Volume betrieben.
- **Redis 7-alpine** wird als separater Container gezogen.

Ollama läuft schon nativ auf dem Host. Das Ziel des Users ist, **alle anderen
Komponenten ebenfalls als systemnahe Pakete** zu installieren statt als
Container.

## 2. Ziele und Nicht-Ziele

**Ziele**

- Ein Single-Host-Setup, in dem Agora, Neo4j, Redis und die Build-Toolchain als
  native Pakete laufen.
- Ein **Bootstrap-Script** (`scripts/install.sh`), das einen Linux-Host (Debian
  12 / Ubuntu 22.04+) idempotent in einen lauffähigen Agora-Host verwandelt.
- **systemd-Units** für `agora-backend`, `agora-frontend`/Reverse-Proxy,
  Neo4j und Redis, sodass nach `reboot` alles selbstständig hochkommt.
- Kein Compose-Build mehr im Standardfall. Docker bleibt als alternativer Pfad
  bestehen, wird aber im README als "Option B" deklassiert.
- **Persistente Daten liegen außerhalb des Repos.** Uploads, Run-State und
  Simulation-Artefakte werden nach `/var/lib/agora/` ausgelagert, damit
  `git pull` und Neuinstallationen Nutzerdaten nicht überschreiben.

**Nicht-Ziele**

- Keine Multi-Host- / Cluster-Installation.
- Keine Distributions-Pakete von Agora selbst (.deb / .rpm) in Phase 1 — Agora
  läuft weiterhin aus einem geklonten Repo, nur die *Abhängigkeiten* werden
  Pakete.
- Keine Windows-Unterstützung. macOS bleibt Best-Effort über Homebrew-Notizen.

## 3. Komponenten-Inventar — Quelle pro Paket

| Komponente | Bisher | Künftig (Linux) | Bezugsquelle |
|---|---|---|---|
| Python ≥ 3.11 | im Container | Distro-Paket | `apt install python3 python3-venv` — Debian 12 liefert nativ 3.11, Ubuntu 24.04 liefert 3.12 (kompatibel zur `>=3.11`-Range in `pyproject.toml`); Ubuntu 22.04 nur via deadsnakes-PPA für 3.11. `python3.11`-Paketnamen explizit zu nageln scheitert auf Ubuntu 24.04. |
| Node.js ≥18 | im Container | NodeSource-Repo | `curl -fsSL https://deb.nodesource.com/setup_20.x \| sudo -E bash -` + `apt install nodejs` |
| `uv` | aus ghcr-Image kopiert | offizielles Astral-Install | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Neo4j 5.18+ Community | Docker-Image | offizielles Neo4j-APT-Repo | `apt install neo4j=1:5.18.*` mit gepinntem Major |
| Redis 7 | Docker-Image | Distro-Paket | `apt install redis-server` (Debian 12: 7.0; für 7.2 ggf. Redis-APT-Repo) |
| Ollama | bereits Host | bleibt | offizielles Ollama-Install-Script |
| APOC für Neo4j | im Compose-Env aktiviert | Plugin-Datei | `neo4j-admin plugin install apoc` oder JAR in `/var/lib/neo4j/plugins/` |

Damit liegen **alle Komponenten** als versionierte System- bzw.
Vendor-Pakete vor und Updates laufen über `apt` / `ollama` / `uv` statt über
Image-Rebuilds.

## 4. Zielarchitektur

```
                 ┌──────────────────────────────────────┐
                 │           systemd auf Host           │
                 │                                      │
  Browser ──────►│ nginx (optional)  :80/:443           │
                 │   ├─► /  → frontend dist (static)    │
                 │   └─► /api → 127.0.0.1:5001          │
                 │                                      │
                 │ agora-backend.service  :5001         │
                 │   gunicorn → Flask-App               │
                 │                                      │
                 │ neo4j.service          :7474/:7687   │
                 │ redis-server.service   :6379         │
                 │ ollama.service         :11434        │
                 └──────────────────────────────────────┘
```

Im Default bleibt Vite NICHT im Hintergrund laufen — stattdessen wird das
Frontend einmal gebaut (`npm run build`) und entweder per `nginx` oder per
Flask-Static ausgeliefert. Das kostet weniger RAM als ein dauerhafter
Vite-Dev-Server und entspricht dem, was eine "Paket-Installation" semantisch
bedeutet: einmal installieren, läuft.

## 5. Bootstrap-Script `scripts/install.sh`

Ein Script, das den Host idempotent vorbereitet. Skizze (verkürzt):

```bash
#!/usr/bin/env bash
set -euo pipefail

# 0. Pre-Checks
require_root_or_sudo
detect_distro                  # Debian 12 | Ubuntu 22.04 | Ubuntu 24.04

# 1. APT-Repos einrichten
add_repo_neo4j                 # debian.neo4j.com, GPG-Key, Pin auf 5.18.*
add_repo_nodesource_20

# 2. Pakete installieren
apt update
apt install -y python3 python3-venv \
               nodejs \
               redis-server \
               neo4j \
               build-essential ca-certificates curl jq
# Auf Ubuntu 22.04 zusätzlich deadsnakes-PPA + python3.11-venv, weil das
# Distro-Default dort 3.10 ist; auf Debian 12 / Ubuntu 24.04 reicht python3.

# 3. uv installieren — systemweit nach /usr/local/bin/, damit die
#    systemd-Unit nicht vom Home-Verzeichnis des agora-Users abhängt.
command -v uv >/dev/null || \
  curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh

# 4. Ollama installieren, wenn nicht vorhanden
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh

# 5. Neo4j konfigurieren
configure_neo4j_initial_password   # neo4j-admin dbms set-initial-password
install_apoc_plugin                # neo4j.conf: dbms.security.procedures.unrestricted=apoc.*
systemctl enable --now neo4j

# 6. Redis konfigurieren (bind 127.0.0.1, supervised systemd)
systemctl enable --now redis-server

# 7. Agora-Repo deployen
deploy_repo_to /opt/agora       # git clone oder rsync, owner agora:agora
install -d -o agora -g agora -m 0750 \
  /var/lib/agora/uploads /var/lib/agora/simulations
# UPLOAD_DIR (und perspektivisch SIMULATION_DIR) in /etc/agora/agora.env
# einpflegen, damit das Backend nicht mehr in den Repo-Pfad schreibt.
sudo -u agora npm run setup:all
sudo -u agora npm run build      # Frontend einmalig bauen

# 8. systemd-Units installieren
install_unit agora-backend.service
install_unit agora-frontend.service   # optional, falls kein nginx
systemctl daemon-reload
systemctl enable --now agora-backend.service

# 9. Modelle vorziehen
sudo -u agora ollama pull qwen3-embedding:4b
sudo -u agora ollama pull qwen3-coder-next:cloud   # optional
```

Das Script muss in jeder Phase **idempotent** sein (`apt install -y`,
`systemctl is-active --quiet ...`, Konfig-Änderungen via `sed -i.bak` mit
Marker-Kommentaren).

## 6. systemd-Units

`/etc/systemd/system/agora-backend.service` (Skizze):

```ini
[Unit]
Description=Agora Flask Backend
After=network-online.target neo4j.service redis-server.service
Wants=neo4j.service redis-server.service

[Service]
Type=simple
User=agora
Group=agora
WorkingDirectory=/opt/agora/backend
EnvironmentFile=/etc/agora/agora.env
ExecStart=/usr/local/bin/uv run gunicorn \
    --workers 2 --bind 127.0.0.1:5001 \
    --worker-class gthread --threads 8 \
    'app:create_app()'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Anmerkungen:

- **Gunicorn statt `python run.py`**: `run.py` startet `app.run(...)` —
  Werkzeug-Dev-Server. Für eine Paket-Installation gehört da ein WSGI-Server
  hin. `gunicorn` kommt als Backend-Dependency mit (oder wird nachgezogen).
- **EnvironmentFile** liegt unter `/etc/agora/agora.env` (chmod 0640, owner
  `root:agora`), damit Secrets nicht im Repo-Pfad liegen. `.env` im
  Repo-Root bleibt für Dev erhalten, aber die Service-Unit liest
  `/etc/agora/agora.env`.
- **Frontend**: Wenn nginx nicht erwünscht ist, kann eine
  `agora-frontend.service` `npm run preview -- --host 127.0.0.1 --port 5173`
  fahren. Sauberer ist `nginx` mit dem statischen `frontend/dist`-Output.

## 7. Frontend-Auslieferung

Zwei Varianten, je nach Reife:

- **A — `nginx`** (empfohlen):
  - Server-Block `listen 80; root /opt/agora/frontend/dist;`
  - `location /api { proxy_pass http://127.0.0.1:5001; ... }`
  - Optional `location /api/simulation/.*/stream { proxy_buffering off; }` für
    SSE.
- **B — Flask serviert `dist/`**: Eine kleine Erweiterung in
  `app/__init__.py`, die im Production-Mode `frontend/dist/index.html` als
  Catch-All ausliefert. Spart einen Daemon, schluckt aber den Vorteil eines
  vorgeschalteten Reverse-Proxy (TLS, Rate-Limit, Caching).

Phase 1 → Variante B als Default (kein zusätzliches Paket); Phase 2 →
optionale nginx-Konfig im Repo unter `scripts/deploy/nginx-agora.conf`.

## 8. Konfigurations- und Secret-Handling

- `cp .env.example /etc/agora/agora.env`, dann `chmod 0640` und Eigentümer
  `root:agora`.
- `SECRET_KEY` und `NEO4J_PASSWORD` werden vom Install-Script generiert
  (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) und sowohl
  in `agora.env` als auch via `neo4j-admin dbms set-initial-password` in Neo4j
  gesetzt.
- `EVENT_BUS_BACKEND=redis` und `REDIS_URL=redis://127.0.0.1:6379/0` werden
  hart gesetzt — der Compose-Override entfällt.
- `LLM_BASE_URL=http://127.0.0.1:11434/v1` und
  `EMBEDDING_BASE_URL=http://127.0.0.1:11434` ersetzen das Compose-spezifische
  `host.docker.internal`.
- **Persistente Datenverzeichnisse außerhalb von `/opt/agora`**: Das
  Install-Script legt `/var/lib/agora/uploads` (chown `agora:agora`, chmod
  0750) und `/var/lib/agora/simulations` an. In `agora.env` werden
  `UPLOAD_DIR=/var/lib/agora/uploads` und — sobald das Backend einen
  entsprechenden Knopf bekommt — `SIMULATION_DIR=/var/lib/agora/simulations`
  gesetzt. Damit überlebt jeder `git pull` und jedes Image-Reroll die
  Nutzerdaten unverändert. Backend-Folge-Ticket: `Config.UPLOAD_FOLDER` muss
  diesen Env-Knopf akzeptieren (heute hardcoded relativ zum Backend-Pfad).

## 9. Update-Pfad

```bash
cd /opt/agora
sudo -u agora git pull --ff-only
sudo -u agora npm run setup:all
sudo -u agora npm run build
sudo systemctl restart agora-backend
```

Optional: `scripts/upgrade.sh`, das genau das in einem Schritt macht und
vorher `npm run check` als Smoke-Test fährt.

## 10. Migration vom heutigen Compose-Setup

1. **Daten sichern**: `docker exec agora-neo4j neo4j-admin database dump
   neo4j --to-path=/data/backups/` und das Volume kopieren.
2. **Compose stoppen**: `docker compose down` (Volumes erst löschen, wenn die
   Native-Installation grün ist).
3. **`scripts/install.sh`** laufen lassen.
4. **Neo4j-Dump einspielen**: `neo4j-admin database load neo4j
   --from-path=/var/lib/neo4j/import`.
5. `backend/uploads/` aus dem alten Bind-Mount nach `/var/lib/agora/uploads/`
   spiegeln (`rsync -a`); analog `backend/uploads/simulations/` nach
   `/var/lib/agora/simulations/`.
6. Smoke-Test: `curl localhost:5001/health` und `curl localhost:5001/api/status`.

## 11. Phasen / Liefer-Inkremente

Die Umsetzung sollte in kleinen, jeweils mergbaren Schritten passieren —
nicht als Big Bang.

- **Phase 1 — Foundation**
  - `scripts/install.sh` (Debian 12 + Ubuntu 24.04) mit Pakete-Install und
    Service-Start, ohne Auto-Setup von Agora selbst.
  - `gunicorn` als Backend-Dep aufnehmen, `run.py` bekommt einen
    Production-Branch oder wir wechseln direkt auf
    `gunicorn 'app:create_app()'`.
  - `docu/installation-paket.md` als User-Doku.
- **Phase 2 — Service & Frontend-Build**
  - `agora-backend.service`, optional `agora-frontend.service`.
  - `npm run build` als fester Schritt im Install-Script.
  - Flask-Static-Catch-All hinter Feature-Flag `AGORA_SERVE_FRONTEND=true`.
- **Phase 3 — Operability**
  - `scripts/upgrade.sh`, `scripts/uninstall.sh`.
  - Optional `scripts/deploy/nginx-agora.conf` + Doku zu TLS via certbot.
  - README-Quickstart umstellen: native Installation als Option A,
    Compose als Option B.
- **Phase 4 — Distribution (optional, später)**
  - `.deb`-Paket für Agora selbst (cdbs/dh\_virtualenv oder fpm), das
    `/opt/agora`, die systemd-Units und einen `agora`-User mitbringt.
  - Damit wird `git clone` für End-User ersetzt durch `apt install agora`
    (eigenes APT-Repo nötig).

## 12. Risiken und offene Fragen

- **Neo4j 5.18-Verfügbarkeit im offiziellen APT-Repo prüfen.** Falls nur
  5.x-„latest" verfügbar ist, muss das Install-Script eine konkrete
  Minor-Version pinnen oder `neo4j-admin` aus dem Tarball nehmen. Sonst
  riskieren wir Major-Bumps zwischen Hosts.
- **APOC-Lizenz und -Bezug**: APOC Core liegt als JAR bei Neo4j; Pfad ins
  `plugins/`-Dir prüfen (`/var/lib/neo4j/plugins/` unter Debian-Paket).
  Versionsmatch zur Neo4j-Minor ist Pflicht.
- **Ollama als systemd-Service unter dem `agora`-User vs. systemweit**:
  Der offizielle Installer legt `ollama.service` unter `ollama:ollama` an. Das
  ist ok, der Backend-Service ruft Ollama nur über HTTP. `ollama pull` muss
  dann aber als `ollama`-User laufen, nicht als `agora`.
- **Python 3.11 auf Ubuntu 22.04**: nur via deadsnakes-PPA. Saubere Lösung ist
  Ubuntu 24.04 als Baseline. 22.04 sollte explizit als Best-Effort
  dokumentiert werden.
- **WSGI-Server-Wahl**: Gunicorn ist konservativ. Wenn SSE-Throughput zur
  Engstelle wird, müssen wir auf `gunicorn -k gevent` oder `uvicorn` mit ASGI
  wechseln — wegen Flask aktuell nicht trivial. Für ein Single-User-Setup ist
  `gunicorn` mit Threads ausreichend.
- **Backend-Knopf für `UPLOAD_DIR`/`SIMULATION_DIR`**: Heute liegt der
  Upload-Pfad in `Config.UPLOAD_FOLDER` relativ zum Backend-Pfad. Phase 1
  braucht ein kleines Backend-Patch, das `UPLOAD_DIR` (und perspektivisch
  `SIMULATION_DIR`) aus der Env akzeptiert — sonst greift die in Sektion 8
  beschriebene Auslagerung nicht. Solange das Patch fehlt, bleibt der
  Symlink `/opt/agora/backend/uploads → /var/lib/agora/uploads` als
  Fallback.

## 13. Akzeptanzkriterien

Phase 1 + 2 sind erfüllt, wenn:

1. Auf einem frischen Debian 12 reicht ein einziger Aufruf von
   `sudo bash scripts/install.sh`, um anschließend einen lauffähigen
   `localhost:5173` zu sehen — ohne Docker.
2. `systemctl status agora-backend neo4j redis-server ollama` ist auf allen
   vier Diensten `active (running)`.
3. `npm run check` läuft auf dem Host grün.
4. Reboot des Hosts → alle Dienste fahren automatisch wieder hoch.
5. `/api/status` meldet `neo4j: ok`, `ollama: ok`, `disk` und `gpu` korrekt.
