# Deployment — Prod-Like

**Stand:** 2026-05-07, Europe/Berlin
**Scope:** Hardened Single-Tenant-Deployment — kein Multi-User-AuthN, aber
Loopback-Bind, Gunicorn, Reverse-Proxy, Token-Pflicht und enge CORS. Zielbild
ist „lokal hinter Tailscale/WireGuard“, **nicht** ein direkt im Internet
exponierter Server.

Für den Entwicklungspfad siehe [`deployment-dev.md`](deployment-dev.md).

> **Wichtig:** Agora hat keinen echten Mehrbenutzer-Auth-Stack. Der
> `AGORA_AUTH_TOKEN`-Guard ist ein Shared-Secret-Bearer. „Prod-Like“ heißt
> hier: alle bekannten Härtungen aktiv, aber Single-User-Vertrauensmodell
> bleibt. Wer das Ding offen ins Internet stellt, übernimmt das Restrisiko.

---

## Voraussetzungen

| Komponente | Mindestversion | Zweck |
|---|---|---|
| Docker | aktuell | Multi-Stage-Build, Compose-Override |
| Docker Compose | 2.24+ | `!override` / `!reset` für Port-Strip |
| Reverse-Proxy | aktuell | Traefik 3.x, Nginx 1.25+ oder Caddy 2.x |
| Tailscale / WireGuard | optional, empfohlen | Tunnel statt Internet-Exposition |
| Ollama | aktuell | LLM + Embedding (auf dem Host) |
| Neo4j | 5.18+ | Graph-Storage (Compose-intern) |

---

## Compose-Prod-Pfad

### Override-Datei

`docker-compose.prod.yml` ist der Override für den Produktionsbetrieb. Er
setzt drei Dinge gegenüber dem Default-Compose:

1. **`build.target: prod`** — Multi-Stage-Dockerfile zieht das schlanke
   Runtime-Stage mit gebautem Frontend-Bundle und Gunicorn vor Flask. Kein
   Node/npm/curl, kein Vite, kein `npm run dev`, kein Bind-Mount auf
   Quellcode. Backend-Dependencies entstehen im `backend-build`-Stage per
   `uv sync --frozen --no-dev`; das finale Image kopiert nur `.venv`,
   Backend-App/Skripte und `frontend/dist`.
2. **`agora.ports: !override [...]`** — Vite-Port (`5173`) entfällt; nur der
   Backend-Port (`5001`) bleibt, gebunden auf `127.0.0.1`. Statisches
   Frontend wird vom Backend ausgeliefert (Flask serviert
   `/app/frontend/dist`); externer Zugriff läuft über den Reverse-Proxy.
3. **`neo4j.ports: !reset []`** — Neo4j Browser (`7474`) und Bolt (`7687`)
   werden im Prod-Override **nicht** auf den Host veröffentlicht. Backend
   redet weiter über das Compose-Netzwerk mit Neo4j; wer aus Ops-Sicht
   Browser-Zugriff braucht, tunnelt explizit (Tailscale-SSH oder
   `docker compose exec neo4j cypher-shell`).
4. **`read_only: true`** — der `agora`-Container läuft im Prod-Override mit
   read-only Root-FS. Schreibpfade sind explizit: `backend/uploads` als
   Volume, plus tmpfs für `/tmp`, `/app/backend/logs`, `/home/agora/.cache`
   und `/home/agora/.gunicorn`.

### Start

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build

docker compose ps
docker compose logs -f agora
```

> Compose-Versionen vor 2.24 fallen für `!reset` auf Array-Merge zurück.
> Effekt: Neo4j erbt die Loopback-Ports vom Default. Nicht ideal, aber
> kein Sicherheitsbruch (`127.0.0.1`). Upgrade auf Compose 2.24+ wird
> empfohlen.

### Was läuft

| Service | Port (Host) | Bind | Zweck |
|---|---|---|---|
| `agora` (Gunicorn) | 5001 | 127.0.0.1 | API + statisches Frontend |
| `neo4j` | — | nur Compose-intern | Bolt + Browser ohne Host-Port |
| `redis` | — | nur Compose-intern | Tickets + Event-Bus |

Das ist die Angriffsfläche aus Sicht des Hosts: ein einziger TCP-Port auf
Loopback. Alles andere bleibt im Compose-Netzwerk.

---

## Gunicorn

Das `prod`-Stage startet:

```text
gunicorn --workers 2 --bind 0.0.0.0:5001 --chdir backend "app:create_app()"
```

`0.0.0.0` ist hier **nicht** das Loophole — der Container ist read-only,
sieht nur das Compose-Netzwerk und der Host-Port liegt auf `127.0.0.1`.
Worker-Count `--workers 2` ist konservativ. Für CPU-bound Workloads über
Compose-Env überschreibbar (eigener `command:`-Override im Prod-File oder
Image-Rebuild mit angepasstem `CMD`).

Multi-Worker hat eine Konsequenz: in-process-State (`signed_ticket._seen`)
ist nicht mehr ausreichend. Single-Use-Tickets gehen seit v0.9.0 / Slice 3
über Redis (`SET … NX EX <ttl>`); ohne Redis fällt der Pfad still auf
in-process zurück und verliert die Multi-Worker-Garantie. Prod-Setup muss
Redis aktiv haben — der Compose-Default tut das.

---

## Reverse-Proxy-Topologien (Sub-Slice 45)

Drei Betriebsvarianten stehen bereit. Die **Sidecar-Nginx**-Variante ist die
Repo-Default-Implementierung (Sub-Slice 45, Closes #106). Traefik und Tailscale
sind dokumentierte Alternativen für bestehende Stacks.

### Sidecar-Nginx — nginx:alpine als Docker-Compose-Sidecar

**Zielszenario:** Minimaler Prod-Stack ohne externe Abhängigkeiten — nginx läuft
als eigener Container im selben Compose-Netzwerk, liefert das statische Frontend-Bundle
aus und reicht API-Calls an den agora-Container durch.

**Voraussetzungen:**
- Docker Compose 2.24+ (`!reset`-Syntax für Port-Strip)
- `frontend/dist` lokal gebaut oder aus dem gebauten Image extrahiert
  (Bind-Mount in den nginx-Sidecar)
- Repo-Root als Arbeitsverzeichnis beim `docker compose`-Aufruf

**Schritt-für-Schritt:**
1. Frontend-Bundle bereitstellen (muss vor Stack-Start aktuell sein).
   Lokaler Build:
   ```bash
   cd frontend && npm ci && npm run build && cd ..
   ```
   Alternativ das exakt im Prod-Image enthaltene Bundle extrahieren:
   ```bash
   rm -rf frontend/dist && mkdir -p frontend
   cid=$(docker create agora-agora:ci-<sha>)
   docker cp "$cid:/app/frontend/dist" ./frontend/dist
   docker rm "$cid"
   ```
2. Drei-File-Stack starten:
   ```bash
   docker compose \
     -f docker-compose.yml \
     -f docker-compose.prod.yml \
     -f deploy/compose/docker-compose.prod-with-proxy.yml \
     up -d --build
   ```
3. Verifikation:
   ```bash
   curl -fsS http://localhost/healthz    # nginx-eigen, kein Backend nötig
   curl -fsS http://localhost/health     # Backend durchgereicht
   curl -fsS http://localhost/           # Frontend-Bundle (200)
   ```
   Alternativ: `bash scripts/verify-deploy.sh` (erkennt den Proxy-Stack automatisch).

**Caveats:**
- Ohne vorher gebautes `frontend/dist` zeigt nginx die nginx-Default-Welcome-Page
  statt der Agora-SPA. Sichtbares Symptom: `curl http://localhost/ | grep -i "Welcome to nginx"`.
- HTTPS-Termination muss extern erfolgen (Tailscale-Funnel, Cloudflare-Tunnel oder
  separater nginx mit Let's Encrypt auf Port 443). Dieser Stack lauscht nur auf HTTP/:80.

---

### Traefik-Labels — für Stacks, die Traefik bereits betreiben

**Zielszenario:** Agora wird in einen bestehenden Traefik-3.x-Stack integriert;
Traefik übernimmt TLS-Termination und Routing.

**Voraussetzungen:**
- Traefik 3.x läuft als Container im selben Docker-Netzwerk
- `--providers.docker.exposedbydefault=false` in der Traefik-Konfiguration
- `certresolver` konfiguriert (ACME / Let's Encrypt)

**Schritt-für-Schritt:**
1. Eigene Override-Datei anlegen (z. B. `docker-compose.traefik.yml`):
   ```yaml
   services:
     agora:
       labels:
         - "traefik.enable=true"
         - "traefik.http.routers.agora.rule=Host(`agora.example.com`)"
         - "traefik.http.routers.agora.tls.certresolver=letsencrypt"
         - "traefik.http.services.agora.loadbalancer.server.port=5001"
         - "traefik.http.routers.agora.middlewares=agora-sse@docker"
         - "traefik.http.middlewares.agora-sse.headers.customresponseheaders.X-Accel-Buffering=no"
   ```
2. Stack mit dem zusätzlichen Override starten.
3. `curl -fsS https://agora.example.com/health` — Backend antwortet über Traefik.

**Caveats:**
- SSE braucht in Traefik besondere Konfiguration: `X-Accel-Buffering=no` per
  Middleware (siehe Label oben) plus Traefik muss mit `--providers.docker.exposedbydefault=false`
  gestartet sein, damit nicht alle Container automatisch exponiert werden.
- Das statische Frontend-Bundle muss separat ausgeliefert werden. Einfachste Option:
  ein zweiter nginx-Container nur für `/usr/share/nginx/html`, oder Traefik liest
  direkt vom Volume. Das ist ein komplexerer Pfad und hier nicht weiter ausgeführt.

---

### Tailscale-Funnel — für Single-User-Setups ohne eigene HTTPS-Infrastruktur

**Zielszenario:** Demo- oder Einzelbenutzer-Setup — Tailscale übernimmt HTTPS und
stellt eine öffentlich erreichbare `*.ts.net`-URL bereit, ohne eigene Zertifikate.

**Voraussetzungen:**
- Tailscale installiert und `tailscale up` ausgeführt
- Sidecar-Nginx läuft auf Port 80 (oder direkt Backend auf 5001)
- Funnel-Feature im Tailnet aktiviert

**Schritt-für-Schritt:**
1. Tailscale verbinden: `tailscale up`
2. Lokalen HTTP-Stack per Tailscale Serve exponieren:
   ```bash
   tailscale serve https / http://127.0.0.1:80
   ```
3. Öffentlichen Funnel aktivieren (optional, macht die URL internet-erreichbar):
   ```bash
   tailscale funnel 443 on
   ```

**Caveats:**
- Funnel-Limits: ein Hostname pro Tailnet, sehr begrenzte Bandbreite, keine
  Custom-Domain. Nur für Demo- oder Einzelbenutzer-Szenarien geeignet — nicht
  für Multi-User-Prod.
- `tailscale funnel` macht die Instanz öffentlich erreichbar. Pflicht-Audit:
  ist das tatsächlich beabsichtigt? `AGORA_AUTH_TOKEN` muss gesetzt sein.

---

## Verifikation

Alle Varianten können mit `bash scripts/verify-deploy.sh` geprüft werden.
Das Skript erkennt automatisch, ob der nginx-Sidecar aktiv ist:

- **Mit Proxy:** smoket `:${AGORA_PROXY_PORT:-80}/healthz` (nginx-eigen),
  `/health` (Backend durchgereicht) und `/` (Frontend, HTTP 200).
- **Ohne Proxy:** prüft Backend direkt auf `127.0.0.1:${AGORA_BACKEND_PORT:-5001}/health`.
- Bei Fehler: gibt `docker compose ps` und nginx-Logs (letzte 20 Zeilen) aus und
  beendet mit Exit-Code 1.

---

## Reverse-Proxy (Altbestand)

<!-- veraltet seit Sub-Slice 45 — die Skizzen unten wurden durch die drei
     Topologie-Sections oben ersetzt. Inhalt bleibt als Referenz erhalten. -->

Traefik, Nginx oder Caddy davorzuschalten ist **Pflicht**, nicht Kür:

- TLS-Termination — Backend selbst spricht kein HTTPS.
- Rate-Limiting — Agora hat keinen eigenen Limiter.
- Cookie-/Header-Hardening (HSTS, `X-Frame-Options`, CSP).
- Optional: HttpOnly-Cookie-Flow als Zielarchitektur (siehe
  [`auth.md`](auth.md), Option C).

### Traefik (Beispiel)

`docker-compose.proxy.yml` (separater Override; im Repo nicht versioniert):

```yaml
services:
  traefik:
    image: traefik:v3.1
    ports:
      - "127.0.0.1:80:80"
      - "127.0.0.1:443:443"
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik/acme.json:/acme.json
  agora:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.agora.rule=Host(`agora.tail-xyz.ts.net`)"
      - "traefik.http.routers.agora.entrypoints=websecure"
      - "traefik.http.routers.agora.tls=true"
      - "traefik.http.services.agora.loadbalancer.server.port=5001"
```

Traefik bindet sich auf Loopback; der eigentliche Tunnel läuft über
Tailscale (siehe nächster Abschnitt). `acme.json` ist optional — innerhalb
eines Tailnets reicht oft das Tailscale-Cert (`tailscale serve` /
`funnel`).

### Nginx (Skizze)

```nginx
server {
    listen 127.0.0.1:443 ssl http2;
    server_name agora.tail-xyz.ts.net;

    ssl_certificate     /etc/ssl/agora/fullchain.pem;
    ssl_certificate_key /etc/ssl/agora/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    client_max_body_size 60m;   # Upload-Limit (PDF) leicht über 50 MB

    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;

        # SSE-Stream (/api/simulation/<id>/stream) braucht keepalive + kein Buffering
        proxy_read_timeout 1h;
        proxy_buffering    off;
    }
}
```

`proxy_buffering off` ist wichtig — der Simulation-Status-Stream geht über
SSE und darf nicht gepuffert werden, sonst kommen Updates erst am Ende des
Runs an.

---

## Tailscale / WireGuard

Empfohlenes Pattern: Reverse-Proxy lauscht auf `127.0.0.1` (oder dem
Tailscale-Interface), und Tailscale stellt den Tunnel.

```bash
# Variante A — Tailscale Funnel (öffentlich erreichbar via *.ts.net)
tailscale serve https / http://localhost:443
# Pflicht-Audit: ist das wirklich beabsichtigt? Funnel = Internet-exposed.

# Variante B — nur im Tailnet (Default, empfohlen)
tailscale serve --bg --https=443 http://localhost:443
```

WireGuard-Setups arbeiten analog: Reverse-Proxy lauscht auf der
WireGuard-IP (z. B. `10.66.0.1`), keine Bindings auf `0.0.0.0`. Das Routing
auf Layer-3 ist explizit, nicht über Container-Port-Publishing.

`AGORA_EXTRA_ORIGINS` aufnehmen, falls das Frontend unter einem anderen
Origin auftaucht (z. B. Tailscale-Hostname mit anderem Port):

```env
AGORA_EXTRA_ORIGINS=https://agora.tail-xyz.ts.net,https://agora.intern.lan
```

---

## CORS- / Auth-Konfiguration

### Pflicht in Prod

```env
FLASK_DEBUG=false
SECRET_KEY=<token_urlsafe(32)>
NEO4J_PASSWORD=<echter_wert>
AGORA_AUTH_TOKEN=<token_urlsafe(32)>
```

Einzeiler für die Geheimwerte:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Wenn `FLASK_DEBUG=false` und `SECRET_KEY` / `NEO4J_PASSWORD` Placeholder
sind (`change-me`, `agora`, `neo4j`, `password`), bricht `Config.validate()`
hart ab. Das ist gewollt — die Liste der abgelehnten Werte steht in
[`security-hardening.md`](security-hardening.md), Phase 1 / Slice 1.

### Was **nicht** gesetzt sein darf

| Variable | Wert | Warum nicht |
|---|---|---|
| `AGORA_CORS_ALLOW_ALL` | `true` | Wildcard-CORS hebelt die Origin-Whitelist aus. Nur für Lab-Setups, nie in Prod. Backend loggt eine Warning, falls aktiv. |
| `AGORA_ALLOW_ANONYMOUS` | `true` | Token-Pflicht aus. Macht `/api/*` öffentlich. |
| `FLASK_DEBUG` | `true` | Tracebacks im Response-Body, Werkzeug-Reloader, Placeholder-Reject inaktiv. |
| `FLASK_HOST` | `0.0.0.0` (im Container ohne Reverse-Proxy davor) | Container ist read-only und im Compose-Netz, aber wenn der Host-Port nicht auf Loopback gebunden ist, exponiert Compose das nach außen. Im Prod-Override liegt der Host-Port auf `127.0.0.1`. |

### CORS-Whitelist

Origins kommen ausschließlich aus zwei Quellen:

1. Statische Defaults `http://localhost:5173`, `http://127.0.0.1:5173` (für
   Dev-Frontend gegen Prod-Backend; bei reinem Container-Frontend irrelevant).
2. `AGORA_EXTRA_ORIGINS` (Komma-separiert) — hier kommen Tailscale-Hostnames
   und LAN-Aliase rein.

Preflight-Verhalten siehe [`security-hardening.md`](security-hardening.md),
Phase 2.

### Frontend-Token-Storage

Prod-Empfehlung: Memory-Mode. Token überlebt keinen Page-Reload, XSS-
Residuum in `localStorage` entfällt:

```env
VITE_AGORA_TOKEN_STORAGE=memory
```

Der Token wird zur Laufzeit im JS-Heap gehalten (`setAgoraToken(...)`).
Konsequenz: nach jedem Reload muss er neu injiziert werden — z. B. durch
einen kommenden `/api/auth/login`-Endpoint oder durch SPA-Bootstrap mit
einem injected Secret. Details und Risiko-Vergleich in
[`auth.md`](auth.md), Abschnitt „Frontend-Token-Storage“.

---

## Compose-DNS

Container-DNS ist konfigurierbar, damit Operatoren Host-/Tailnet-Resolver
erzwingen können, ohne das Compose-File zu patchen:

```env
AGORA_DNS_PRIMARY=8.8.8.8
AGORA_DNS_SECONDARY=8.8.4.4
```

Default bleibt Google-DNS, weil Docker Desktop auf manchen macOS-Versionen
IPv6-DNS aktiviert, sobald Ports gebunden werden. Für interne Resolver die
beiden Werte in `.env` überschreiben.

## Neo4j

Im Prod-Override hat Neo4j keinen Host-Port. Konsequenzen:

- **Browser-Zugriff** für Ad-hoc-Cypher: `docker compose exec neo4j
  cypher-shell -u neo4j -p $NEO4J_PASSWORD`. Wer den Browser braucht,
  öffnet den Port temporär oder läuft per SSH-Forward (`ssh -L
  7474:127.0.0.1:7474 …`).
- **Image und Memory-Settings** sind per Env parametrierbar. Defaults:
  `NEO4J_IMAGE=neo4j:5.18-community`,
  `NEO4J_HEAP_INITIAL=512m`, `NEO4J_HEAP_MAX=2g`,
  `NEO4J_PAGECACHE_SIZE=4g`. Bei kleineren Hosts vor Start in `.env`
  überschreiben; nicht direkt im Compose-File patchen.
- **Backups** über `neo4j-admin database dump` aus dem Container-Kontext;
  zugehörige Cron-/Restore-Strategie ist Folge-Sub-Slice F3 (siehe
  [`2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md)).

---

## Ollama

Ollama läuft auf dem Host, nicht im Container. Begründung: GPU-Zugriff,
Modell-Updates, RAM-Footprint. Zwei Konsequenzen:

- Auf Linux-Hosts nutzt der Container `host.docker.internal` (per
  `extra_hosts: host-gateway` im Compose). Auf einem Host ohne GPU läuft
  Ollama im CPU-Modus — Latenz steigt deutlich, aber API-Vertrag bleibt.
- Ollama selbst sollte **nicht** auf `0.0.0.0` lauschen. Default
  `127.0.0.1:11434` reicht; Docker erreicht den Loopback-Port über die
  `host-gateway`-Bridge.

GPU-Status sichtbar unter `/api/status` (`ollama_uses_gpu`).

---

## Update-Pfad

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d \
  --no-deps --force-recreate agora
docker image prune -f
```

Vor dem Update prüfen:

- [`dependency-risk-register.md`](dependency-risk-register.md) — gibt es
  neue CVE-Findings, die einen Pin freigeben?
- `CHANGELOG.md` — `[Unreleased]` und letzter Tag, ob Migrations-Schritte
  nötig sind (z. B. neue `.env`-Variable, Schema-Migration).

---

## Rollback

Image-Tag pinnen statt blind `latest`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  pull agora || true
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d agora
```

Im Bedarfsfall den Backend-Container auf den vorherigen SHA setzen
(`image: ghcr.io/arn0ld87/agora@sha256:…`) und `up -d --no-deps agora`
neu starten. Neo4j-Daten bleiben im Volume — Rollback ist nur ein
Image-Switch, keine Datenmigration.

---

## Release-Pipeline (CI/CD)

Die GitHub Actions Workflow-Datei `.github/workflows/docker-image.yml`
implementiert seit Sub-Slice N1 eine smoke-gegattete Drei-Job-Pipeline.
Kein Image landet in einer Registry, bevor der End-to-End-Smoke grün ist.

### Job-Reihenfolge

| Trigger | Job-Kette |
|---|---|
| `main`-Push | `build-only` → `prod-proxy-smoke` → `publish` (alle drei strikt) |
| `tag`-Push (`v*`) | `build-only` → `prod-proxy-smoke` → `publish` (Smoke strikt) |
| `release/**` oder `rc/**` | `build-only` → `prod-proxy-smoke`; PRs nach `main` laufen denselben teuren Smoke |
| Workflow-Dispatch | wie `main`-Push; Publish nur mit grünem Smoke oder explizitem `force_publish=true` |

### Job-Beschreibungen

1. **`build-only`** — Buildx-Build ohne `push: true`. Image wird als
   `agora-agora:ci-<sha>` getaggt, als `/tmp/image.tar` exportiert und
   via `actions/upload-artifact@v4` gespeichert. GHA-Cache
   (`cache-to: type=gha,mode=max`) beschleunigt den Publish-Rebuild.

2. **`prod-proxy-smoke`** — `needs: [build-only]`. Lädt das Artefakt
   (`actions/download-artifact@v4`), importiert das Image via
   `docker load -i image.tar`, taggt es als `agora-agora:latest` damit
   Compose es ohne `--build` aufnimmt, extrahiert `frontend/dist` aus genau
   diesem Image und führt den vollständigen Sidecar-Nginx-Stack-Smoke durch.
   Tag-Pushes sind strikt; es gibt keinen `success() || tag`-Bypass mehr.

3. **`publish`** — `needs: [prod-proxy-smoke]`. Führt den Buildx-Build
   erneut durch (praktisch instant dank GHA-Cache-Hit), schreibt mit
   `push: true` alle GHCR-Tags als Pflichtpfad und versucht danach denselben
   Tag-Satz als optionalen Docker-Hub-Mirror. Docker-Hub-Fehler blockieren den
   GHCR-Release-Pfad nicht, werden aber im Workflow sichtbar. `latest` wird
   nur bei Push auf den Default-Branch gesetzt, nicht bei Tags.

### Begründung der Artefakt-Variante

`actions/upload-artifact` wurde gegenüber dem reinen Buildx-GHA-Cache-
Ansatz bevorzugt, weil:
- Das Artefakt ist deterministisch und benannt — kein Cache-Key-Missverständnis.
- Parallele Workflow-Runs auf demselben SHA können sich keinen Cache
  gegenseitig überschreiben.
- `docker load` ist explizit und auditierbar; ein Cache-only-Ansatz lädt
  das Image implizit beim Build-Step, was schwerer zu debuggen ist.

Verweis: [PLAN.md N1](../PLAN.md), Arbeitsprotokoll
[`docu/2026-05-04-n1-docker-publish-order-arbeitsprotokoll.md`](2026-05-04-n1-docker-publish-order-arbeitsprotokoll.md).

---

## Verweise

- [`deployment-dev.md`](deployment-dev.md) — Dev-Setup ohne Hardening.
- [`auth.md`](auth.md) — Token-Vertrag, Ticket-Flow, Storage-Optionen.
- [`security-hardening.md`](security-hardening.md) — Phase 1/2/3 + P1
  CI-Security-Scans + Slice 3 Redis-Tickets.
- [`dependency-risk-register.md`](dependency-risk-register.md) — aktive
  CVE-Baseline und Aufräum-Prozess.
- [`SECURITY_REVIEW_SUMMARY.md`](SECURITY_REVIEW_SUMMARY.md) — historischer
  Review-Stand (vor v0.9.0).
