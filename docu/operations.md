# Operations

**Stand:** 2026-05-07, Europe/Berlin
**Scope:** Was ein Ops-Mensch (oder Future-Alex um 02:30 Uhr) wissen muss,
um den Stack zu beobachten, zu reparieren und zu verstehen, warum etwas
gerade nicht geht. Single-User-Vertrauensmodell — kein Pager-Setup, keine
SLA, kein Multi-Tenant.

Verwandte Dokumente:
- [`backup-restore.md`](backup-restore.md) — Datensicherung und Recovery.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Hardening-Pflicht.
- [`security-threat-model.md`](security-threat-model.md) — Boundaries und
  Restrisiken.
- [`auth.md`](auth.md) — Token-Vertrag.

---

## Healthchecks

### `GET /health` (öffentlich)

Liveness-Probe. Antwortet immer `200` mit:

```json
{ "status": "ok", "service": "Agora Backend" }
```

Kein Auth nötig. Vom Docker-Healthcheck verwendet. Im finalen Prod-Image
läuft die Probe ueber Python `urllib`, damit kein `curl` im Runtime-Image
benoetigt wird. Reverse-Proxy-Healthchecks zeigen ebenfalls hierhin.

### `GET /api/status` (auth-pflichtig in Prod)

Aggregierte Komponenten-Sicht. Antwortet immer `200` (defensiv — keine
Komponente schickt 5xx hoch):

```json
{
  "success": true,
  "backend": { "ok": true, "version": "0.9.0" },
  "neo4j": {
    "reachable": true,
    "uri": "bolt://neo4j:7687",
    "is_connected": true,
    "last_success_ts": "2026-05-01T17:30:42+00:00"
  },
  "ollama": { "reachable": true, "models": [...], "default_model": "..." },
  "disk":   { "uploads": { "used_gb": ..., "free_gb": ... } },
  "gpu":    { "ollama_uses_gpu": true, "vram_gb": 8.5, "hints": [...] },
  "timestamp": "2026-05-01T17:30:42.123456+00:00"
}
```

Wichtige Felder zum Beobachten:

| Feld | Bedeutung | Was tun, wenn rot? |
|---|---|---|
| `neo4j.reachable: false` | Bolt-Treiber kommt nicht durch | Container-Status prüfen, `NEO4J_PASSWORD`, Memory-Settings (Pagecache 4 GB im Default). |
| `ollama.reachable: false` | LLM-Endpoint nicht ansprechbar | Ollama-Service prüfen (`systemctl status ollama` / `ollama serve`), `LLM_BASE_URL` in `.env`. |
| `gpu.ollama_uses_gpu: null` | Ollama nicht erreichbar oder GPU-Probe leer | Ollama-Logs ansehen; `nvidia-smi` separat prüfen. |
| `disk.uploads.free_gb < 5` | Bind-Mount geht voll | Uploads aufräumen (`backend/uploads/<sim_id>/`) oder Disk vergrößern. |

---

## Logs

### Quellen

| Logger | Wo | Format |
|---|---|---|
| `agora.*` (Python) | Container: `/app/backend/logs/<YYYY-MM-DD>.log` (tmpfs in Compose); Bare-Metal: `backend/logs/<YYYY-MM-DD>.log` | text (Default) oder JSON via `AGORA_LOG_FORMAT=json` |
| Console / stdout | `docker compose logs -f agora` | spiegelt Logger ab Level INFO |
| Gunicorn-Access | stderr, von Compose mitgesnatcht | text |
| Vite (Dev-Stage) | stdout, von Compose mitgesnatcht | text |
| Neo4j | Compose-Volume `neo4j_logs`, Container-Pfad `/logs/` | text |
| OASIS-Subprozess | `backend/uploads/<sim_id>/console.log` plus Redis-Bus-Topics | text |

### Konfiguration

| Env | Default | Effekt |
|---|---|---|
| `AGORA_LOG_FORMAT` | `text` | `json` schaltet auf strukturierte Zeilen für zentrale Auswertung. |
| `LOG_DIR` (implizit) | `backend/logs/` | wird beim Start angelegt; im Compose ein tmpfs (max 64 MB). |
| Rotation | `RotatingFileHandler`, 10 MB / 5 Backups | pro Tag eine Datei, pro Datei max 50 MB History. |

### Logger-Redaction

`install_redaction_filter()` blendet im Logger Bearer-Tokens, `?token=`,
`?ticket=`, sowie als Secret markierte API-Keys (siehe
[`security-hardening.md`](security-hardening.md), Slice 5 + Followup
`9d566b1`). Das gilt für `agora.*`-Logger, **nicht** automatisch für
direkte `print()`-Calls oder Subprozess-Logs.

### Was im Log steht — Cheat Sheet

| Zeilen-Marker | Bedeutung |
|---|---|
| `agora.config WARNING` | `.env`-Drift, Placeholder-Reject im Nicht-Debug-Modus, fehlende Pflicht-Variablen. Im Dev nur Warning, in Prod fail-fast. |
| `Auth: AGORA_AUTH_TOKEN aktiv` | Token-Guard läuft. Erscheint einmal beim Startup. |
| `Auth: AGORA_AUTH_TOKEN nicht gesetzt — /api/* ist offen` | Open-Mode. In Prod ein Pflicht-Alarm. |
| `CORS: AGORA_CORS_ALLOW_ALL=true — alle Origins erlaubt. NICHT in Prod` | Wildcard-CORS aktiv. |
| `Storage health: NOT CONNECTED (...)` | Neo4j-Driver hat Verbindungsfehler beim Probe. |
| `vision cap reached: 40 calls pro Upload` | Vision-Cap (`VISION_MAX_CALLS_PER_UPLOAD`) gegriffen — Upload hat unverhältnismäßig viele Bilder. |
| `signed_ticket: redis unavailable, falling back to in-process _seen` | Multi-Worker-Single-Use-Garantie weg. Redis prüfen. |

---

## Ressourcenbedarf

Anhaltswerte aus dem aktuellen Default-Stack (qwen3-coder-next:cloud,
qwen3-embedding:4b lokal). Werte sind grob — kein Benchmark, kein SLA.

| Komponente | Idle | Last (Graph-Build, Simulation) |
|---|---|---|
| Flask-Backend (Gunicorn 2 Worker) | ~250 MB RSS | ~1–2 GB RSS während Ingestion + Embedding |
| Neo4j 5.18 (Compose-Defaults: Heap 512 MB-2 GB, Pagecache 4 GB) | ~1.5 GB RSS | ~5–7 GB RSS bei mittelgroßen Graphen (~50k Knoten) |
| Redis 7-alpine | ~10 MB RSS | <50 MB RSS (Tickets + Pub/Sub) |
| Frontend (Vite Dev-Stage) | ~300 MB RSS | ~500 MB RSS während Build |
| Ollama (Host) | je Modell — `qwen2.5:32b` ~22 GB VRAM bzw. RAM | nur während aktiver Generierung |
| OASIS-Subprozess | je nach Persona-Anzahl | ~500 MB-1 GB RSS pro aktive Simulation |

Disk-Bedarf:

- `backend/uploads/` wächst mit jedem Run. Eine Simulation mit ~50
  Personas + Console-Log + Snapshot kommt auf 50–200 MB. Aufräumen
  ist manuell — siehe [`backup-restore.md`](backup-restore.md).
- `backend/.cache/huggingface/` einmalig ~1.1 GB für OASIS-Modelle
  (Twitter/twhin-bert-base). Persistiert zwischen Restarts.
- `neo4j_data` Volume — typisch ~1–5 GB pro mittelgroßem Graph.

GPU-Probe:

- `/api/status.gpu.ollama_uses_gpu` ist `true`/`false`/`null`. Quelle ist
  Ollama REST `/api/ps`, nicht `nvidia-smi` — kein NVIDIA Container
  Toolkit nötig, solange Ollama auf dem Host läuft.

---

## Ausfälle und was tun

### Neo4j down

**Symptom:** `/api/status.neo4j.reachable: false`. Ingestion bricht mit
`ServiceUnavailable`. Frontend zeigt Toast „Service nicht erreichbar".

**Diagnose:**

```bash
docker compose ps neo4j
docker compose logs --tail 200 neo4j
docker compose exec neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN 1"
```

**Häufige Ursachen:**

- `NEO4J_PASSWORD` in `.env` falsch oder fehlt. Compose bricht beim Start
  ab (`:?`-Syntax); im laufenden Stack passiert das nicht spontan.
- Pagecache-OOM: bei großen Graphen zieht Neo4j `pagecache_size=4g` plus
  Heap. Wenn der Host zu klein ist, killt das OOM den Container.
  Anpassen in `docker-compose.yml`, Neo4j-Service, `NEO4J_server_memory_*`.
- Volume-Fehler: `neo4j_data` korrupt nach Stromabbruch. Recovery-Pfad:
  `docker compose down`, `docker volume inspect agora_neo4j_data`,
  ggf. Restore aus Dump (siehe [`backup-restore.md`](backup-restore.md)).

**Fallback:** Backend lebt weiter, aber Graph-Endpoints liefern 503.
Simulation-Run-State liegt in `state.json` und übersteht den Ausfall;
Reports gehen nicht durch, weil ReportAgent Graph-Tools braucht.

### Redis down

**Symptom:** Log-Zeile `signed_ticket: redis unavailable, falling back to
in-process _seen`. Event-Bus fällt auf File-Polling zurück.

**Diagnose:**

```bash
docker compose ps redis
docker compose exec redis redis-cli ping
```

**Konsequenzen:**

- Single-Use-Tickets greifen nur noch innerhalb eines Workers.
  Multi-Worker-Replay-Schutz weg — Auswirkung gering bei
  Single-User-Setup, kritisch sobald jemand `?ticket=…` aus mehreren
  Tabs gleichzeitig benutzt.
- Live-Status-Stream (SSE) bekommt File-Polling als Transport. Latenz
  steigt; korrekt bleibt es trotzdem.

**Fallback-Schalter:** `EVENT_BUS_BACKEND=file` in `.env` zwingt das
Backend dauerhaft auf File-IPC, falls Redis dauerhaft hin ist.

### Ollama down

**Symptom:** `/api/status.ollama.reachable: false`. Ontology-Generierung
und Report-Generierung scheitern mit `LLM_UNAVAILABLE`.

**Diagnose:**

```bash
curl http://localhost:11434/api/tags
ollama list
ps aux | grep ollama
```

**Häufige Ursachen:**

- Ollama-Service nicht gestartet. Bare-Metal: `systemctl start ollama`.
- Modell nicht vorhanden. `ollama pull qwen2.5:32b`.
- VRAM voll. `ollama ps`; ggf. Modell entladen oder kleineres Modell
  wählen.
- Im Container: `host.docker.internal` löst nicht auf. Linux braucht
  `extra_hosts: host-gateway` (im Compose gesetzt).

**Fallback:** `LLMClient.chat` retryt automatisch über
`llm_call_with_retry` auf 5xx/Timeout/RateLimit. Bei dauerhafter
Ausfall — ohne LLM kein Graph-Build, kein Report. Simulation-Subprozess
kann auch nicht mehr starten.

### Backend liefert 5xx auf jeden API-Call

**Symptom:** Gleichmäßige 500er, kein Komponentenfehler in `/api/status`.

**Diagnose:**

```bash
docker compose logs --tail 500 agora | grep -E "ERROR|Traceback"
```

**Häufige Ursachen:**

- `Config.validate()` failed im Nicht-Debug-Modus (Placeholder-Secrets,
  fehlender `SECRET_KEY`). Container-Startup bricht eigentlich ab —
  wenn der Stack lebt, greift fail-fast nicht.
- Embedding-Mismatch: `EMBEDDING_MODEL` und `VECTOR_DIM` passen nicht
  zusammen. Backend-Boot bricht im Probe.
- Neo4j-Schema-Drift nach manuellem Cypher-Eingriff.

**Fix-Reihenfolge:** Logs lesen, `.env` gegen `.env.example` diffen,
Container neu hochfahren mit `docker compose up -d --force-recreate
agora`.

### Disk voll (`backend/uploads`)

**Symptom:** `disk.uploads.free_gb` knapp; Uploads scheitern mit
`UPLOAD_TOO_LARGE`-irrelevanten Fehlern (Schreibfehler).

**Behandlung:** Alte Simulationen löschen — pro `simulation_id` einen
Ordner unter `backend/uploads/`. Vorher per Run-Dashboard prüfen, ob die
Daten noch gebraucht werden (Reports lesen Graph-Daten, nicht Uploads).

```bash
# Disk-Aufschlüsselung
du -sh backend/uploads/* | sort -h | tail -20

# Älteste Simulationen
ls -1t backend/uploads/ | tail -10
```

### Container restartet im Loop

**Symptom:** `docker compose ps` zeigt `Restarting (n)`.

**Diagnose:**

```bash
docker compose logs --tail 200 agora
docker inspect agora --format '{{json .State}}' | jq
```

**Häufige Ursachen:**

- Health-Check failed → Compose-Restart-Policy `unless-stopped` triggert.
  Backend braucht ~30 s zum Starten (Embedding-Probe, Neo4j-Connect),
  Healthcheck-`start-period` ist 5 s — zu kurz, kann False-Positive
  werfen. Nicht kritisch, solange Backend dann „on“ bleibt.
- Neo4j nicht ready, `depends_on.condition: service_healthy` blockiert.
  Startup-Reihenfolge ist Neo4j → Redis → Agora; wenn Neo4j 30+ s zum
  Hochfahren braucht, geht das Compose-Healthcheck durch (`start-period:
  30s`), aber der Agora-Container wartet.

---

## Routine-Aufgaben

| Trigger | Aktion |
|---|---|
| Neue Version | `git pull` + `docker compose -f docker-compose.yml -f docker-compose.prod.yml build agora` + `up -d --no-deps --force-recreate agora`. Siehe [`deployment-prod-like.md`](deployment-prod-like.md). |
| Neue Dependency | `npm audit` lokal, dann `pip-audit`-Job auf CI. CVEs ohne Upstream-Fix → Eintrag in [`dependency-risk-register.md`](dependency-risk-register.md). |
| Backup | tägliches Neo4j-Dump + Uploads-Snapshot, siehe [`backup-restore.md`](backup-restore.md). |
| Restore-Drill | Quartalsweise. Restore aus Backup auf Test-Volume, Smoke-Test gegen `/api/status`. |
| `.env`-Rotation | `SECRET_KEY` und `AGORA_AUTH_TOKEN` mindestens zweimal jährlich oder bei Verdacht. Container-Restart pflicht. |
| Log-Volumen prüfen | bei tmpfs (Compose) max 64 MB; bei Bare-Metal Disk im Auge behalten. Rotation greift, aber `console.log`-Subprozess-Logs nicht. |

---

## Quellen, die nicht hier stehen

- Code-Pfade je Komponente: README-Architektur-Block.
- API-Verträge: [`api-contracts.md`](api-contracts.md).
- Sicherheits-Phasenchronik: [`security-hardening.md`](security-hardening.md).
- CI-Stages: `.github/workflows/ci.yml`.
