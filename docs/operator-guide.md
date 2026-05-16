# Agora Operator Guide

**Stand:** 2026-05-15
**Scope:** Komplette Anleitung für Operatoren, die eine Agora-Instanz
installieren, betreiben, aktualisieren und im Fehlerfall debuggen
müssen. Single-User-Setup auf Tailnet oder hinter Reverse-Proxy.
**Related:**
[`docs/deployment.md`](./deployment.md) · [`docs/deployment-prod-like.md`](./deployment-prod-like.md) ·
[`docs/backup-restore.md`](./backup-restore.md) ·
[`docs/secret-key-lifecycle.md`](./secret-key-lifecycle.md) ·
[`docs/security-hardening.md`](./security-hardening.md).

---

## 0. Voraussetzungen

- **Host:** Linux x86_64 oder macOS (Apple Silicon). Mindestens 8 GB RAM,
  4 vCPU, 40 GB freier Plattenplatz für `neo4j_data` + `backend/uploads`.
- **Docker:** `docker` ≥ 24 mit Compose v2 (`docker compose`), nicht
  `docker-compose`. Auf Linux Hosts: Compose-User in der `docker`-Gruppe
  oder Root-Login akzeptieren.
- **uv (Python):** für lokale Hilfsskripte (z. B.
  `llm-secrets-doctor.py`). Installation via
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Reverse-Proxy:** Pflicht für jeden Public-Expose — Tailscale-VPN,
  Cloudflare-Tunnel oder nginx/Caddy mit TLS. Default-Compose bindet
  Backend ans Loopback, daher kein direktes Internet-Exposure möglich
  (auch nicht über IPv6).
- **DNS / Tailnet:** Hostname (`agora.tail<id>.ts.net`) für Tailnet-Setup;
  öffentliches A-Record + ALPN für Public-Mode.

---

## 1. Initial-Install

### 1.1 Repo holen

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
```

### 1.2 `.env` mit Secrets befüllen

`.env.example` ist die Vorlage. Erforderliche Variablen:

| Var | Pflicht | Bedeutung |
|---|---|---|
| `SECRET_KEY` | ja | Flask-Session/CSRF-Token. ≥ 32 zufällige Bytes (base64). |
| `AGORA_AUTH_TOKEN` | ja (Prod) | Master-Token für `/api/*`; clients schicken `X-Agora-Token`. |
| `AGORA_SECRET_KEY` | ja (sobald Multi-Provider-Hub genutzt) | Fernet-Master-Key für `backend/data/llm_provider_secrets.json`. **Verlust = Datenverlust.** Siehe `docs/secret-key-lifecycle.md`. |
| `NEO4J_PASSWORD` | ja | Neo4j-User `neo4j`. |
| `LLM_API_KEY` | optional | Fallback-Key wenn UI keinen Provider konfiguriert hat. |
| `LLM_BASE_URL` / `EMBEDDING_BASE_URL` | optional | Override für Provider-URL. Standard ist `host.docker.internal:11434` (Ollama auf Host). |
| `VITE_AGORA_TOKEN` / `ALLOW_BUILD_TIME_TOKEN` | optional | Frontend-Build-Time-Token-Gate, nur für Single-User-Tailnet-Deploys. |

Generieren der drei Crypto-Keys:

```bash
# Flask SECRET_KEY (32 Bytes base64)
python -c 'import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())'

# Auth-Token (Hex)
python -c 'import secrets; print(secrets.token_hex(32))'

# Fernet AGORA_SECRET_KEY (44-Zeichen base64)
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Werte in `.env` einfügen, `chmod 600 .env`, **nicht versionieren**.

### 1.3 Stack starten

```bash
# Dev/Test
docker compose up -d --build

# Prod-like (Loopback-Bind, gunicorn, read_only rootfs)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Erster Start dauert 8–15 Min (Neo4j-Init + Image-Build + HuggingFace-Cache).

### 1.4 Health-Check

```bash
curl -fsS http://localhost:5001/health
# → {"ok":true}

# Mit Auth-Token (Prod):
AGORA_AUTH_TOKEN=$(grep AGORA_AUTH_TOKEN .env | cut -d= -f2)
curl -fsS -H "X-Agora-Token: $AGORA_AUTH_TOKEN" http://localhost:5001/api/status
```

Verify-Deploy als One-Liner:

```bash
bash scripts/verify-deploy.sh
# Mit Persistenz-Smoke (schreibt einen Smoke-Provider-Key, restartet, prüft Erhalt):
AGORA_AUTH_TOKEN=$AGORA_AUTH_TOKEN bash scripts/verify-deploy.sh --full
```

---

## 2. Provider-Key-Verwaltung

### 2.1 Über die UI

1. Login mit `AGORA_AUTH_TOKEN` (UI-Modal beim ersten Aufruf).
2. **Settings → LLM Provider → Add Key.**
3. Provider auswählen (OpenAI, Google, Anthropic, Together, Ollama, …).
4. API-Key einfügen → **Save**.
5. Optional: **Validate** → Key wird gegen `GET /v1/models` des Providers
   geprüft, Status erscheint in der Maske (`ok` / `failed`).

Daten:

- Klartext wird im Backend zu Fernet-Ciphertext und in
  `backend/data/llm_provider_secrets.json` (Mode `0600`) abgelegt.
- Die UI sieht nur den `masked_value` (`sk-...abcd`).
- `AGORA_SECRET_KEY` aus `.env` ist der Decrypt-Key.

### 2.2 Über die CLI (Doctor-Script)

```bash
# Status — welche Provider sind gespeichert?
uv run --project backend python scripts/llm-secrets-doctor.py status

# Roundtrip-Test — jeden Eintrag einmal decryptieren
uv run --project backend python scripts/llm-secrets-doctor.py verify
```

Vollständige Subcommand-Doku: [`docs/secret-key-lifecycle.md`](./secret-key-lifecycle.md).

### 2.3 Workspace-Routing-Defaults

Bestimmt, welches Modell pro Pipeline-Stage genutzt wird, wenn der Run
keinen expliziten Override mitgibt.

```bash
# Aktuelle Defaults lesen
curl -fsS -H "X-Agora-Token: $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/llm/routing/defaults | jq

# Global-Default setzen
curl -fsS -X PUT \
  -H "X-Agora-Token: $AGORA_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider_id":"openai","model":"gpt-4o-mini"}' \
  http://localhost:5001/api/llm/routing/defaults/global
```

Persistiert in `backend/data/workspace_llm_routing.json` (Mode `0600`,
prozesssicher mit `fcntl.flock`).

---

## 3. Backup & Restore

Komplette Tabelle der Assets in [`docs/backup-restore.md`](./backup-restore.md).
Kurz-Routine:

| Asset | Backup-Frequenz | Restore-Tool |
|---|---|---|
| Neo4j-Graph (Compose-Volume `neo4j_data`) | täglich `neo4j-admin database dump` oder Btrfs-Snapshot | `neo4j-admin database load` |
| `backend/uploads/` | stündlich Restic (`--tag agora-fs`) | `restic restore latest` |
| `backend/data/` (Multi-Provider-Hub) | täglich Restic mit demselben Tag | `restic restore` + `chown 1000:1000` |
| `backend/instance/settings.json` | täglich | trivial copy-restore |
| `.env` (inkl. `AGORA_SECRET_KEY`) | jede Rotation **separat** sichern | Passwort-Manager |
| `backend/reports/` | täglich Restic | `restic restore` |

Recovery-Drill: einmal pro Quartal auf einer Test-Maschine durchspielen.
Pflicht.

---

## 4. Update-Prozess

```bash
# 1. State sichern
bash scripts/verify-deploy.sh             # Pre-Update-Smoke
docker compose stop agora
docker compose exec neo4j neo4j-admin server stop
# Neo4j-Dump (siehe docs/backup-restore.md)

# 2. Code pullen
git fetch origin
git log --oneline HEAD..origin/main       # Was kommt?
git pull --ff-only origin main

# 3. Stack neu bauen
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --build

# 4. Migration (falls Changelog welche nennt)
docker compose exec agora uv run --project backend python -m app.migrate

# 5. Verify
AGORA_AUTH_TOKEN=… bash scripts/verify-deploy.sh --full
```

Bei Migration-Fehler: `docker compose down`, Neo4j-Volume aus Backup
wiederherstellen, alten Git-Stand auschecken, Container neu starten.

---

## 5. Fehlerdiagnose

### 5.1 Standard-Diagnose-Befehle

```bash
# Container-Health
docker compose ps
docker compose exec agora curl -fsS http://localhost:5001/health

# Logs (letzte 100 Zeilen)
docker compose logs agora --tail=100
docker compose logs neo4j --tail=100

# Schreibrechte auf backend/data?
docker compose exec -T agora test -w /app/backend/data && echo "OK"

# Mode 0600 für Provider-Secrets-File?
docker compose exec -T agora stat -c '%a' /app/backend/data/llm_provider_secrets.json

# Secret-Store-Doctor
uv run --project backend python scripts/llm-secrets-doctor.py status
uv run --project backend python scripts/llm-secrets-doctor.py verify
```

### 5.2 Typische Symptome

| Symptom | Mögliche Ursache | Erster Schritt |
|---|---|---|
| `/api/status` 503, „Secret store unavailable" | `AGORA_SECRET_KEY` fehlt oder ist invalid in `.env` | `llm-secrets-doctor.py status` |
| Provider-Maske nach Restart leer | `backend/data` nicht persistent gemountet | `docker compose config | grep backend/data` |
| `LLMClient: LLM_API_KEY not configured` | `.env` fehlt im Repo-Root oder Var nicht gesetzt | `cat .env | grep LLM_API_KEY` |
| `/api/status` „Neo4j offline — NoneType" | Fork-Reset im Storage; behoben in #443. Falls trotzdem auf älterer Version: Backend restarten | `docker compose restart agora` |
| Run-Status hängt bei `persona_generation` | OASIS-Subprozess hat keinen Kontext, Memory-Floor nicht aktiv | Logs prüfen, ggf. `LLM_CONTEXT_LIMIT` setzen |
| Frontend-Bundle leer / 404 | `docker compose up` ohne `--build` nach Code-Update | `docker compose up -d --build` |

### 5.3 Wo welche Logs?

| Was | Wo |
|---|---|
| Backend (Flask + gunicorn) | `docker compose logs agora` |
| OASIS-Subprozess | `backend/uploads/<sim_id>/console.log` |
| Neo4j | `docker compose logs neo4j` |
| Run-Status / Audit | `/api/runs/<id>/status` + ReportLogger-Files unter `backend/reports/<sim_id>/audit/` |

---

## 6. Security-Hinweise

- **Niemals direkt aus dem Internet** ohne Reverse-Proxy mit Auth.
  Tailscale oder Cloudflare-Tunnel sind erste Wahl. Compose bindet
  Backend defaultmäßig ans Loopback (`127.0.0.1:5001`), aber dieser
  Schutz gilt nur, solange die Default-Compose nicht durch
  `0.0.0.0`-Overrides übergangen wird.
- **`.env` ist die einzige Datei mit Klartext-Secrets im Repo-Tree.**
  `chmod 600 .env`, niemals in `git add -A`, nie in Pull-Requests
  einfügen.
- **`AGORA_SECRET_KEY` separat vom Repo sichern.** Das ist der
  Decrypt-Key für alle Provider-API-Keys; Verlust bedeutet, dass
  `backend/data/llm_provider_secrets.json` zur unbrauchbaren Datei
  wird. Recovery-Pfad in
  [`docs/secret-key-lifecycle.md`](./secret-key-lifecycle.md#verlust-verhalten).
- **API-Key-Rotation:** Cloud-Provider-Keys (OpenAI, Anthropic, …)
  pro Quartal rotieren. `AGORA_SECRET_KEY` mindestens jährlich oder
  nach Leak-Verdacht. Doctor-Script `rotate` automatisiert den
  Re-Encrypt-Schritt.
- **`backend/data/` ist ab #450 aus dem git-Tracking entfernt.** Falls
  ihr ein älteres Repo updatet, prüft `git log -- backend/data` — ein
  Force-Push-History-Rewrite ist eine separate Security-Aktion, keine
  Slice-Operation.
- **HIGH/CRITICAL CVE-Findings:** Trivy läuft jetzt blockierend (`exit-code: 1`).
  Dokumentierte Upstream-Blocker sind in `.trivyignore` hinterlegt.
  Bei Hardstop-Datum 2026-07-30 muss die Ignore-Liste leer sein oder via
  ADR explizit verlängert (siehe
  [`docs/dependency-risk-register.md`](./dependency-risk-register.md)).
- **Logs enthalten keine Secrets:** `app.utils.logger.install_redaction_filter`
  maskiert `?token=`, `Bearer …` und API-Key-Fragmente. Vor jedem
  Diagnose-Bundle-Export trotzdem manuell durchsehen.

---

## 7. Checkliste (Operator-DoD)

Pre-Deploy:

- [ ] Alle vier Crypto-Secrets in `.env` gesetzt (`SECRET_KEY`,
      `AGORA_AUTH_TOKEN`, `AGORA_SECRET_KEY`, `NEO4J_PASSWORD`).
- [ ] `.env` hat Mode `600`.
- [ ] `docker compose config` zeigt `./backend/data:/app/backend/data` und
      `./backend/instance:/app/backend/instance` als Bind-Mounts.
- [ ] Reverse-Proxy steht (Tailscale-MagicDNS oder TLS-Zertifikat).
- [ ] Restic-Repo + Cronjob für `backend/data` + `backend/uploads` aktiv.
- [ ] `AGORA_SECRET_KEY`-Recovery-Plan (Passwort-Manager-Eintrag) ist
      dokumentiert.

Post-Deploy:

- [ ] `bash scripts/verify-deploy.sh` grün.
- [ ] `bash scripts/verify-deploy.sh --full` grün (Persistenz-Smoke).
- [ ] `uv run --project backend python scripts/llm-secrets-doctor.py status` ok.
- [ ] Erster Test-Run startet ohne Auth-/Provider-Fehler.
