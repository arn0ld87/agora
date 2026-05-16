# Security Hardening — Changelog und Migrations-Hinweise

**Stand:** 2026-05-07, Europe/Berlin
**Ausgelöst durch:** Veröffentlichung des Repos auf GitHub (`github.com/arn0ld87/agora`). Parallel-Audit durch Claude (general-purpose) und Codex (rescue). Ergebnisberichte sind im Review-Transcript dokumentiert; dieses Dokument listet die daraus umgesetzten Fixes und die nötigen Env-Änderungen für bestehende Deployments.

> Kurzfassung: Der Backend lief vorher als unauthentifizierter, `0.0.0.0`-gebundener Prototyp mit wildcard-CORS, Debug-Defaults, statischem Secret-Key und Default-Neo4j-Passwort. Nach den drei Phasen ist die Angriffsfläche auf ein loopback-gebundenes, token-geschütztes API mit restriktivem CORS, Prod-tauglichen Defaults und SSRF-/Injection-Hardenings reduziert.

---

## Phase 1 — Config-Hardening

### Ziel
Prod-tauglich-by-default: keine bekannten Konstanten als Fallback für kryptografische und Auth-relevante Werte.

### Änderungen

| Datei | Änderung |
|---|---|
| `backend/app/config.py` | `FLASK_DEBUG` Default `'True'` → `'False'`. `SECRET_KEY` ohne Code-Default (`os.environ.get('SECRET_KEY') or ''`). `validate()` erzeugt Ephemeral-Key im Dev-Modus, scheitert in Prod mit fehlendem Key. |
| `backend/run.py` | Bind-Default `FLASK_HOST` von `0.0.0.0` → `127.0.0.1`. Docker-Container-Overrides bleiben via Env möglich. |
| `Dockerfile` | `ENV FLASK_HOST=0.0.0.0` setzt den Container-Bind explizit (damit die Compose-Port-Publikation weiter funktioniert). |
| `docker-compose.yml` | `NEO4J_AUTH=${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-agora}` → `${NEO4J_PASSWORD:?NEO4J_PASSWORD muss in .env gesetzt sein}`. Compose bricht ab, wenn das Passwort fehlt. |
| `.env.example` | `SECRET_KEY`, `FLASK_DEBUG`, `FLASK_HOST`-Kommentar ergänzt. `NEO4J_PASSWORD` als Pflichtfeld markiert. |

### Warum
- **Tracebacks aus API-Responses:** Der bestehende Code hat bereits `traceback.format_exc() if Config.DEBUG else None` in ~40 Error-Handlern. Mit dem neuen Default `FLASK_DEBUG=False` greift das automatisch; kein Code-Churn im API-Layer nötig.
- **SECRET_KEY-Default `'agora-secret-key'`:** Bekannter String im öffentlichen Repo. Signierte Session-Cookies / itsdangerous-Tokens damit sind trivial fälschbar. Jetzt: fehlt die Env, failt `validate()` im Nicht-Debug-Modus hart; im Dev-Modus wird ein Ephemeral-Key pro Prozess generiert.
- **Neo4j-Passwort-Default:** Default `neo4j/agora` mit veröffentlichten Ports `7474`/`7687` = unauth DB-Zugriff.
- **Bind-Default:** `0.0.0.0` in einem Dev-Setup ist klassische unerwartete Netzwerk-Exposition. Docker setzt den Override explizit.

### Migration
```bash
# .env ergänzen
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
FLASK_DEBUG=true          # nur lokal. In Prod weglassen.
NEO4J_PASSWORD=<echter_wert>
```

### Verifikation
- `uv run python -c "from app.config import Config; print(Config.validate())"` → `[]`
- `create_app()` erstellt die App, Blueprints `graph`, `simulation`, `report` laden.
- Ohne `SECRET_KEY` und `FLASK_DEBUG=false` → `validate()` liefert Error, `run.py` terminiert mit `sys.exit(1)`.

---

## Phase 2 — Auth + CORS

### Ziel
Netzwerk-Exposition absichern: CORS auf bekannte Origins, Token-Auth für alle `/api/*`-Routen, `/health` bleibt öffentlich.

### Änderungen

| Datei | Änderung |
|---|---|
| `backend/app/__init__.py` | `CORS(app, resources={r"/api/*": {"origins": "*"}})` → Whitelist `['http://localhost:5173', 'http://127.0.0.1:5173']` + optional `AGORA_EXTRA_ORIGINS` (Komma-separiert). Wildcard nur via `AGORA_CORS_ALLOW_ALL=true` mit Log-Warning. `supports_credentials=True`. |
| `backend/app/utils/auth.py` (neu) | `install_blueprint_guard(bp)`, `token_required`-Decorator, `log_auth_mode()`. Token-Extraktion aus `X-Agora-Token`, `Authorization: Bearer …` oder `?token=` (Fallback für `send_file`-Downloads). Vergleich timing-safe via `hmac.compare_digest`. |
| `backend/app/__init__.py` | Jedes API-Blueprint bekommt `install_blueprint_guard(bp)` vor der Registrierung. Auth-Modus wird beim Start geloggt. |
| `frontend/src/api/index.js` | Axios-Request-Interceptor hängt `X-Agora-Token` aus `localStorage.agora_token` oder `VITE_AGORA_TOKEN` an jeden Request. |

### Warum
- **Wildcard-CORS + keine Auth:** jede Website konnte per `fetch()` die API ansprechen, inklusive `DELETE /api/graph/project/<id>`.
- **Keine Auth auf dem LAN-Port:** Tailnet-Peers, Docker-Host-Co-Tenants und andere Netzwerk-Nachbarn konnten destructive Endpoints aufrufen.
- **Opt-in statt Pflicht:** Ohne `AGORA_AUTH_TOKEN` läuft der Server als Open-Mode mit Log-Warning weiter. Gewollt, damit bestehende Dev-Setups nicht sofort brechen. In Prod muss der Token gesetzt werden — die Warnung macht es unübersehbar.

### Migration (Auth scharfschalten)
```bash
# Backend
AGORA_AUTH_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

# Frontend (im Browser-Devtool auf der Agora-Seite)
localStorage.setItem('agora_token', '<der_gleiche_wert>')
```

Ohne gesetzten Env-Wert verhält sich der Server wie vorher, gibt aber beim Start ein Warning aus.

### Verifikation (Flask Test-Client)
| Fall | Ergebnis |
|---|---|
| `/health` public | 200 |
| `/api/graph/data/<id>` ohne Token (Auth aktiv) | 401 `unauthorized` |
| `/api/graph/data/<id>` falscher Token | 401 |
| `/api/graph/data/<id>` korrektes `X-Agora-Token` | durch |
| `/api/graph/data/<id>` korrekter `Authorization: Bearer …` | durch |
| `/api/graph/data/<id>?token=…` korrekt | durch |
| CORS Preflight von `http://localhost:5173` | `Access-Control-Allow-Origin: http://localhost:5173` |
| CORS Preflight von `https://evil.com` | kein `Access-Control-Allow-Origin`-Header |
| CORS Preflight von `AGORA_EXTRA_ORIGINS`-Eintrag | durchgelassen |

### Neue Env-Variablen

| Variable | Default | Zweck |
|---|---|---|
| `AGORA_AUTH_TOKEN` | leer | Wenn gesetzt, verlangt jede `/api/*`-Route den Token. Leer = Open-Mode mit Warning. |
| `AGORA_EXTRA_ORIGINS` | leer | Komma-separierte zusätzliche CORS-Origins (z.B. Tailnet-Hostnames). |
| `AGORA_CORS_ALLOW_ALL` | `false` | Wildcard-CORS. Nur für Ausnahmefälle; loggt Warning. |

---

## Phase 3 — Endpoint-Härtung

### Ziel
Einzelne Vektoren schließen, die auch nach Auth+CORS noch Missbrauchspotenzial haben (authentifizierter Angreifer, Prompt-Injection über Data-Flows, interne Netzwerk-Pivots).

### 3.1 — SSRF-Hardening in `fetch_url`

**Datei:** `backend/app/services/web_tools.py`

**Änderung:** Neuer Helper `_is_public_url(url)` macht einen DNS-Lookup und prüft via `ipaddress.ip_address`-Flags gegen `is_private`, `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`, `is_unspecified`, sowie explizit gegen `169.254.169.254` (AWS-Metadata) und `fd00:ec2::254`. `fetch_url` ruft den Check vor dem Tavily-Request auf und loggt den Reject-Grund.

**Warum:** Tavily fetcht die URL zwar extern, aber Defense-in-Depth gegen (a) DNS-Namen, die auf interne IPs zeigen, (b) Fehlkonfigurationen des Upstream-Proxys, (c) künftigen direkten-Fetch-Code-Pfad.

**Verifikation:** Alle `127.0.0.1`, `localhost`, `10.0.0.1`, `192.168.1.1`, `169.254.169.254`, `[::1]` werden rejected; `example.com`, `alexle135.de` passieren. `ftp://` rejected.

### 3.2 — Profile-Endpoint Key-Whitelist

**Datei:** `backend/app/api/simulation.py` (Route `POST /<simulation_id>/profiles`)

**Änderung:** Der bestehende blinde Merge `for k, v in data.items(): new_profile[k] = v` ist durch eine explizite Whitelist ersetzt (`followers_count`, `following_count`, `favourites_count`, `listed_count`, `verified`, `status`, `location`, `language`, `activity_level`, `time_zone`). Nicht primitive Werte werden verworfen. Unbekannte Keys werden geloggt und verworfen.

**Warum:** Persona-Felder werden vom OASIS-Subprozess in System-Prompts gespiegelt. Ein blinder Merge war ein Prompt-Injection-Vektor — ein Angreifer konnte beliebige Keys (`system_override: "Ignoriere alle Regeln…"`) einschleusen und damit Agenten-Verhalten manipulieren, inklusive Tool-Calls (`WebTools`, `GraphTools`) wenn `ENABLE_AGENT_TOOLS=true`.

### 3.3 — Vision-Call-Cap

**Datei:** `backend/app/utils/file_parser.py`

**Änderung:** `_VisionHelper` bekommt zwei neue Attribute: `calls_made` und `max_calls` (aus Env `VISION_MAX_CALLS_PER_UPLOAD`, Default 40). `describe()` erhöht den Counter erst *nach* dem Cap-Check und bricht bei Überlauf mit einmaligem Warning und leerem Rückgabestring ab. Der PyMuPDF-Text-Layer bleibt erhalten, nur Vision-Beschreibungen für weitere Bilder fallen weg.

**Warum:** `POST /api/graph/ontology/generate` nimmt 50 MB PDFs. Mit `ENABLE_PDF_VISION=true` (Default im Committed-`.env.example`) und `VISION_MODEL_NAME=gemini-3-flash-preview:cloud` wird jedes eingebettete Bild über dem Size-Threshold an ein bezahltes Vision-Modell geschickt. Ein präpariertes PDF mit hunderten kleinen Bildern (knapp über dem Pixel-Area-Threshold) hat das Kostenbudget gehebelt. Selbst mit Auth aktiv ist der Cap Defense-in-Depth.

**Verifikation:** Unit-Check mit `VISION_MAX_CALLS_PER_UPLOAD=3` und einem gefaktem `client.describe_image` → erste drei Calls gehen durch (`ok`), vierter Call triggert Warning "vision cap reached", Return `""` ab dann für alle weiteren Calls.

**Neue Env-Variable:**

| Variable | Default | Zweck |
|---|---|---|
| `VISION_MAX_CALLS_PER_UPLOAD` | `40` | Maximale Vision-LLM-Aufrufe pro Upload-Request. |

### 3.4 — Neo4j Label-Sanitization

**Datei:** `backend/app/storage/neo4j_storage.py`

**Änderung:** Neuer Helper `_sanitize_label(value)` erzwingt Cypher-safe-Identifier-Form für LLM-gelieferte Entity-Typen. Regex-Whitelist `^[A-Za-z_][A-Za-z0-9_]{0,49}$`. Vorverarbeitung: Strip, Whitespace → Underscore, sonstige Non-ASCII/Non-Identifier-Zeichen raus. Rückgabe `None` bei leer, `Entity`-Literal oder wenn nach Normalisierung kein gültiger Identifier entsteht. `add_text`-Codepfad ruft den Sanitizer an der einzigen f-string-Label-Stelle auf (Zeile 286) und interpoliert nur das bereinigte Ergebnis.

**Warum:** Cypher kann Labels nicht per `$parameter` binden — Labels sind syntaktisch Identifier, keine Werte (Neo4j-Doku bestätigt). Die bestehende Zeile `SET n:\`{etype}\`` nahm den Typ aus dem NER-Output blind in ein f-string. Ein Angreifer konnte durch ein präpariertes Upload-Dokument den LLM dazu bringen, einen Entity-Type mit Backticks im Namen zu liefern — damit hätte sich das Backtick-Quoting schließen und eine weitere Cypher-Klausel anhängen lassen. Der Sanitizer normalisiert stattdessen alle Angriffsmuster zu harmlosen Identifiern (z.B. `` `; DROP GRAPH `` → `_DROP_GRAPH`) und akzeptiert nur Ergebnisse, die das Regex-Muster erfüllen.

**Alternative geprüft:** `apoc.create.addLabels(n, [$label])` würde das Label als Parameter akzeptieren, setzt aber APOC im Neo4j-Container voraus und ersetzt die Regex-Prüfung nicht (sonst bleibt der Graph mit beliebigen Label-Namen verseucht). Wir bleiben bei `SET n:\`$label\`` mit striktem Sanitizer, weil der Blast-Radius kleiner ist und keine APOC-Dependency eingeführt wird.

**Verifikation:** Unit-Check gegen 13 Input-Fälle. Legitime Labels (`Person`, `Organization`, `_Internal`, `Film`) bleiben durch. Angriffsmuster (Backticks, Cypher-Fragmente) werden bereinigt, nicht mehr interpretierbar. `Entity`, leer, `None`, >50-Zeichen, mit-Ziffer-beginnend werden verworfen.

---

## Neue / geänderte Env-Variablen (Gesamtübersicht)

| Variable | Pflicht | Default | Zweck |
|---|---|---|---|
| `SECRET_KEY` | ja im Nicht-Debug-Modus | leer | Flask-Session-/Token-Signing. |
| `FLASK_DEBUG` | nein | `false` | Tracebacks in API-Responses, Werkzeug-Reloader. |
| `FLASK_HOST` | nein | `127.0.0.1` (Host), `0.0.0.0` (Docker via `Dockerfile`-ENV) | Bind-Adresse. |
| `NEO4J_PASSWORD` | ja | — (Compose bricht ab) | Neo4j-Auth. |
| `AGORA_AUTH_TOKEN` | empfohlen | leer | API-Bearer-Token. |
| `AGORA_EXTRA_ORIGINS` | nein | leer | Zusätzliche CORS-Origins. |
| `AGORA_CORS_ALLOW_ALL` | nein | `false` | Wildcard-CORS; löst Warning aus. |
| `AGORA_PROXY_FIX_X_FOR` | nein | `0` | Anzahl vertrauenswürdiger Proxies, deren `X-Forwarded-For` Flask für `request.remote_addr` auswertet. Im Repo-Sidecar-Proxy-Compose auf `1` gesetzt. |
| `AGORA_PROXY_FIX_X_PROTO` | nein | `0` | Anzahl vertrauenswürdiger Proxies, deren `X-Forwarded-Proto` Flask für das Request-Schema auswertet. Im Repo-Sidecar-Proxy-Compose auf `1` gesetzt. |
| `AGORA_PROXY_FIX_X_HOST` / `AGORA_PROXY_FIX_X_PORT` / `AGORA_PROXY_FIX_X_PREFIX` | nein | `0` | Weitere Werkzeug-`ProxyFix`-Zähler. Nur setzen, wenn ein vertrauenswürdiger Proxy diese Header kontrolliert. |
| `VISION_MAX_CALLS_PER_UPLOAD` | nein | `40` | Hartes Cap für Vision-LLM-Calls pro PDF-Upload. |
| `AGORA_DNS_PRIMARY` / `AGORA_DNS_SECONDARY` | nein | `8.8.8.8` / `8.8.4.4` | Compose-DNS-Resolver fuer Container. |
| `NEO4J_IMAGE` | nein | `neo4j:5.18-community` | Neo4j-Image-Pin fuer Compose. |
| `NEO4J_HEAP_INITIAL` / `NEO4J_HEAP_MAX` / `NEO4J_PAGECACHE_SIZE` | nein | `512m` / `2g` / `4g` | Neo4j-Memory-Tuning ohne Compose-Patch. |

---

## Runtime-Image-Hardening (v1.0 Phase 3)

**Stand:** 2026-05-07

Das finale `prod`-Image erbt nicht mehr vom Build-Stage mit Node/npm/curl.
Die Build-Kette ist getrennt:

1. `frontend-build` baut `frontend/dist` mit Node/npm.
2. `backend-build` fuehrt `uv sync --frozen --no-dev` aus.
3. `prod` basiert auf `python:3.11-slim`, kopiert nur `.venv`,
   Backend-App/Skripte und `frontend/dist`, laeuft als User `agora` und
   nutzt einen Python-basierten Healthcheck.

Der Prod-Compose-Pfad setzt fuer `agora` `read_only: true`. Schreibpfade sind
explizit erlaubt: `backend/uploads` als Volume sowie tmpfs fuer `/tmp`,
`/app/backend/logs`, `/home/agora/.cache` und `/home/agora/.gunicorn`.

Lokale Verifikation fuer Phase 3:

```bash
docker build --target prod -t agora-runtime-after-phase3 .
docker run --rm agora-runtime-after-phase3 which node  # exit != 0
docker run --rm agora-runtime-after-phase3 python -c "import shutil; print(shutil.which('npm'), shutil.which('curl'))"
docker compose -f docker-compose.yml -f docker-compose.prod.yml config | grep -A4 'read_only: true'
```

Image-Groesse im lokalen Vergleich: 747 MB vor Phase 3, 320 MB nach Phase 3
(-427 MB, -57 %).

---

## Supply-Chain-Hardening (v1.0 Phase 4)

**Stand:** 2026-05-07

Neue Gates:

| Workflow | Trigger | Zweck |
|---|---|---|
| `.github/workflows/dependency-review.yml` | `pull_request` | Blockiert neue Dependency-Funde ab `high`. |
| `.github/workflows/codeql.yml` | `push` auf `main`, `pull_request` nach `main`, woechentlich, manuell | CodeQL fuer Python und JavaScript/TypeScript. |
| `.github/workflows/docker-image.yml::publish` | nur nach gruenem Prod-Smoke | GHCR-Push, Build-Provenance-Attestation und SPDX-JSON-SBOM-Artefakt. |

Alle neu eingefuehrten Actions sind auf volle Commit-SHAs gepinnt. Dependabot
bleibt fuer `github-actions` aktiv und aktualisiert SHA-Pins mit
Versionskommentar.

Verifikation einer veroeffentlichten Image-Attestation:

```bash
gh auth login
docker login ghcr.io
gh attestation verify \
  oci://ghcr.io/arn0ld87/agora:<tag> \
  --repo arn0ld87/agora \
  --signer-workflow .github/workflows/docker-image.yml
```

Das SBOM liegt im erfolgreichen `publish`-Job als Artefakt
`agora-ghcr-sbom-spdx`.

---

## F2.1 — VITE_AGORA_TOKEN per Build-Arg-Gate (Sub-Slice 46)

**Stand:** 2026-05-03

**Problem.** Frueher zog der Frontend-Build-Stage des Dockerfile den Wert
von `VITE_AGORA_TOKEN` automatisch aus der Build-Env (Compose liest das
implizit aus `.env`) und brannte ihn als Plaintext ins Frontend-Bundle.
Wer das Bundle in die Hand bekam (per `docker save`, `docker pull`,
oder dem statisch ausgelieferten `frontend/dist`), bekam den Token.

**Fix.** Das Einbrennen ist jetzt hinter einem expliziten Build-Arg
`ALLOW_BUILD_TIME_TOKEN` (Default `false`) gelockt.

### Default-Pfad — Token nicht im Bundle

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Build sieht den Token nicht (auch wenn `VITE_AGORA_TOKEN` in `.env`
gesetzt ist). Frontend-Bundle hat einen leeren `import.meta.env.VITE_AGORA_TOKEN`.
Der Operator setzt den Token zur Laufzeit über das UI-Eingabefeld
(siehe `frontend/src/api/index.ts:setAgoraToken`).

### Opt-In — Token im Bundle (Single-User-Tailnet-Deploy)

```bash
docker build \
  --target prod \
  --build-arg ALLOW_BUILD_TIME_TOKEN=true \
  --build-arg VITE_AGORA_TOKEN="<dein-token>" \
  -t agora-with-token .
```

**Caveats:**
- Nur für Single-User-Tailnet-Deploys oder lokale Entwicklung gedacht.
- Niemals für Public-Internet-Deploys: jeder, der das Bundle abgreift,
  bekommt den Token.
- Token-Rotation erfordert einen vollständigen Image-Rebuild.

### Auth-Header

In beiden Pfaden schickt das Frontend den Token als
`X-Agora-Token`-Header (nicht als `?token=`-Query-Parameter — siehe
F2.2 Sub-Slice 47 für das Hard-Disable des Query-Fallbacks).

### Neue Build-Args

| Build-Arg | Default | Zweck |
|---|---|---|
| `ALLOW_BUILD_TIME_TOKEN` | `false` | Explizites Gate. Nur bei `true` wird `VITE_AGORA_TOKEN` ins Bundle einkompiliert. |
| `VITE_AGORA_TOKEN` | leer | Der einzubrennende Token. Wird ohne `ALLOW_BUILD_TIME_TOKEN=true` ignoriert. |

---

## Offene Punkte (nach Phase 3 abgearbeitet)

- Upstream-Review-Status aus `SECURITY_REVIEW_SUMMARY.md` ist durch diese Phasen teilweise überholt; der Abschnitt dort wird in einem Follow-up abgeglichen.
- ~~Langfristig: echte Session-/Login-Auth statt Static-Token.~~ Durch [ADR-0001](decisions/0001-auth-model.md) (2026-05-04, Accepted) beantwortet: v1.0 bleibt **bewusst Single-User-only**, ein echtes Session-/Login-Modell ist v2-Material. Siehe Sektion „Auth-Modell v1.0" am Ende dieses Dokuments.

---

## P1 — CI-Security-Scans und sichere Error-Envelopes

**Stand:** 2026-04-29, Europe/Berlin

### Ziel

Security-Regressions früher erkennen und interne Exception-Details aus produktionsnahen API-Responses entfernen.

### Änderungen

| Datei | Änderung |
|---|---|
| `.github/workflows/ci.yml` | Neuer Job `security` mit `npm audit --audit-level=high`, `uv export` + `pip-audit` und Gitleaks Secret Scan. |
| `.gitleaksignore` | Zwei historische False Positives fingerprint-genau gebaselined; neue Secret-Findings bleiben blockierend. |
| `backend/uv.lock` | 39 Python-Advisories durch konservative Lockfile-Upgrades beseitigt. |
| `backend/app/utils/api_responses.py` | 500/504 aus `@handle_api_errors` nutzen sichere Standardmeldungen plus `code`; konkrete Exception-Details nur bei `Config.DEBUG=true`. |
| `backend/app/utils/api_responses.py` | Generische `/api/*`-Handler für `HTTPException` und ungefangene Exceptions ergänzen die zentrale JSON-Envelope. |
| `backend/tests/test_api_responses.py` | Regression-Tests für nicht-leakende 5xx-Responses und generische Framework-Fehler ergänzt. |

### Response-Contract

```json
{
  "success": false,
  "error": "internal server error",
  "code": "internal_error"
}
```

Im Debug-Modus kann zusätzlich `debug_error` und `traceback` erscheinen. Dieser Modus bleibt lokale Entwicklung und Tests vorbehalten.

### CI-Checks

```bash
# Frontend Dependency Audit
cd frontend
npm audit --audit-level=high

# Backend Runtime Dependency Audit aus uv.lock
cd ../backend
uv export --frozen --no-dev --no-hashes --no-emit-project \
  --format requirements.txt --output-file /tmp/agora-backend-requirements.txt \
  > /dev/null
uvx pip-audit --strict \
  --ignore-vuln CVE-2026-25990 \
  --ignore-vuln CVE-2026-40192 \
  --ignore-vuln CVE-2026-42308 \
  --ignore-vuln CVE-2026-42310 \
  --ignore-vuln CVE-2026-42311 \
  --ignore-vuln CVE-2025-71176 \
  --ignore-vuln CVE-2026-1839 \
  --ignore-vuln CVE-2024-46455 \
  --ignore-vuln CVE-2025-64712 \
  -r /tmp/agora-backend-requirements.txt
```

Gitleaks läuft in GitHub Actions mit vollständiger Historie (`fetch-depth: 0`). Bei echten Findings gilt: Secret sofort rotieren, Commit-Historie separat bereinigen und erst danach das Finding suppressen.

Lokaler Smoke-Check:

```bash
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest \
  detect --source=/repo --redact=100 --no-banner
```

---

## Slice 3 — Redis-basierte Single-Use-Tickets (v0.9.0)

**Datum:** 2026-05-01

### Ziel

Die in-process `_seen`-Menge in `consume()` schützt vor Replay nur innerhalb
eines Workers. Unter gunicorn mit mehreren Workern kann das gleiche Ticket
mehrfach eingelöst werden.

### Änderungen

| Datei | Änderung |
|---|---|
| `backend/app/utils/signed_ticket.py` | `consume()` versucht zuerst atomisches `SET ticket:<sig> 1 NX EX <ttl>` gegen Redis. Erfolgreiches `True` → ok, `False`/`None` → Replay oder Fallback. In-Memory-Pfad bleibt mit `logger.debug` als Fallback. |
| `backend/tests/test_signed_ticket_redis.py` | 6 Cases: Replay-Block via Redis, Multi-Worker-Simulation, In-Memory-Fallback + Warning. |
| `backend/pyproject.toml` | `fakeredis[lua]>=2.30.0` in `dev`-Group ergänzt. |

### Warum
- `?ticket=<signed>` wird für SSE-Streams und Download-Links verwendet.
- Ein Ticket ist 60 s gültig und scope-bound (`sse:<sim_id>`).
- Multi-Worker-Deployments (gunicorn, Docker-Swarm, k8s) brauchen einen
  shared Store für die Single-Use-Garantie.

### Verifikation
- `uv run pytest tests/test_signed_ticket.py tests/test_signed_ticket_redis.py -v` → 16 passed.

### Migration
- Keine — Redis wird via `REDIS_URL` (bereits im Default-Compose vorhanden)
  automatisch erkannt. Fehlt Redis, fällt `consume()` lautlos auf den
  in-process-Pfad zurück.

---

### Temporäre Baseline

Die neun `pip-audit`-Ignores sind durch feste Upstream-Pins blockiert:

| Advisory | Paket | Upstream-Pin |
|---|---|---|
| `CVE-2026-25990`, `CVE-2026-40192`, `CVE-2026-42308`, `CVE-2026-42310`, `CVE-2026-42311` | `pillow==10.3.0` | `camel-oasis==0.2.5` pinnt `pillow==10.3.0`; `camel-ai==0.2.78` begrenzt `pillow<11`. |
| `CVE-2025-71176` | `pytest==8.2.0` | `camel-oasis==0.2.5` pinnt `pytest==8.2.0`. |
| `CVE-2026-1839` | `transformers==4.57.6` | `sentence-transformers==3.0.0` begrenzt `transformers<5`. |
| `CVE-2024-46455`, `CVE-2025-64712` | `unstructured==0.13.7` | `camel-oasis==0.2.5` pinnt `unstructured==0.13.7`. |

Die Baseline muss beim nächsten `camel-oasis`-/`camel-ai`-Upgrade erneut geprüft und reduziert werden.

---

## Auth-Modell v1.0 (ADR-0001, Accepted 2026-05-04)

**Stand:** 2026-05-04. Siehe [`docs/decisions/0001-auth-model.md`](decisions/0001-auth-model.md) für die volle ADR mit Optionen-Vergleich und Begründung.

### Garantie

Agora v1.0 ist **Single-User-only**. Ein einziger gemeinsamer Bearer-Token (`AGORA_AUTH_TOKEN`) ist der einzige Auth-Principal. Es gibt:

- kein User-Konzept,
- keine Login-Page,
- keinen Logout (außer „Token aus dem Frontend-Storage löschen"),
- keine Token-Rotation ohne Container-Neustart,
- keinen Audit-Trail wer wann was getan hat,
- keine Rollen oder Berechtigungen,
- keine Multi-User-Tenancy.

`/api/status.backend.auth_mode` liefert seit 2026-05-04 explizit `"single_user_token"` (vorher: `"token"`), damit Operatoren sofort sehen, dass dies kein Multi-User-Modell ist.

### Was Auth schützt — und was nicht

**Schützt:**

- Unbefugten API-Zugriff auf `/api/*` ohne Token (`401`).
- Token-Leak durch URL-bound Endpunkte: `?token=` ist im Non-Debug-Modus geblockt; SSE/Downloads laufen über kurzlebige Signed Tickets (60 s TTL, scope-bound).
- Token-Leak via Frontend-Bundle: `Dockerfile` baut den Token nicht ein (`ALLOW_BUILD_TIME_TOKEN=false` als Default).
- Bekannte Konfigurations-Fehler: `Config.validate()` lehnt Start ab bei fehlendem `SECRET_KEY`/`AGORA_AUTH_TOKEN`/`NEO4J_PASSWORD`.

**Schützt nicht:**

- Brute-Force auf den Token außerhalb von `POST /api/auth/ticket`. M10.5 hat app-seitige Fixed-Window-Limits für Signed-Ticket-Issuance, den Upload-Pfad `POST /api/graph/ontology/generate`, die Simulation-LLM-Trigger `POST /api/simulation/generate-profiles` + `POST /api/simulation/prepare` und die Report-Trigger `POST /api/report/generate` + `POST /api/report/chat` ergänzt. Bis zu einem verteilten Rate-Limiter gilt weiter: niemals direkt im Internet exponieren.
- Mehrbenutzer-Konflikte: bei zwei Personen mit demselben Token gibt's keine Sitzungstrennung.
- Audit-Compliance (DSGVO, SOC2, ISO 27001 für Multi-User): nicht erfüllbar in v1.0.
- Session-Hijacking nach Token-Leak: ohne Logout-Endpunkt muss der Token rotiert werden (Prozedur unten).

### Token-Rotation-Prozedur

Bei Verdacht auf Token-Leak (z.B. Token in Logs aufgetaucht, Frontend-Bundle versehentlich gepublisht, Mitarbeiter-Wechsel mit Wissen über den Token):

1. **Neuen Token generieren:**
   ```bash
   AGORA_AUTH_TOKEN_NEW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
   ```
2. **`.env` auf dem Server aktualisieren:**
   ```bash
   sed -i.bak "s|^AGORA_AUTH_TOKEN=.*|AGORA_AUTH_TOKEN=${AGORA_AUTH_TOKEN_NEW}|" .env
   ```
3. **Container neu starten** (Compose wartet, bis Backend `health: healthy` ist):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     -f deploy/compose/docker-compose.prod-with-proxy.yml \
     up -d --force-recreate agora
   docker compose ps
   ```
4. Frontend mit neuem Token versorgen — bei Default-Setup (ALLOW_BUILD_TIME_TOKEN=false) muss der Operator den Token zur Laufzeit über das UI-Eingabefeld im Frontend setzen; ein Rebuild des Frontend-Bundles ist nicht erforderlich. Bei ALLOW_BUILD_TIME_TOKEN=true muss das Frontend-Bundle neu gebaut werden:
   ```bash
   ALLOW_BUILD_TIME_TOKEN=true VITE_AGORA_TOKEN="${AGORA_AUTH_TOKEN_NEW}" \
     docker compose -f docker-compose.yml -f docker-compose.prod.yml build agora
   docker compose up -d --force-recreate agora
   ```
5. **Verifikation:**
   ```bash
   curl -fsS -H "X-Agora-Token: ${AGORA_AUTH_TOKEN_NEW}" http://localhost/api/status | jq .
   # → "auth_mode": "single_user_token"
   curl -fsS -H "X-Agora-Token: alter_token" http://localhost/api/status
   # → 401 Unauthorized
   ```
6. **Alle aktiven Browser-Sessions abmelden** durch Hard-Reload und Frontend-localStorage-Cleanup; alte Tokens funktionieren ab Neustart sofort nicht mehr.

**Kein File-System-State geht verloren** — Neo4j-Daten, Uploads und Simulationen bleiben unberührt.

### Trigger für ein neues Auth-Modell (ADR-0001 Supersedes)

Wenn **eine** der folgenden Bedingungen wahr wird, ist ein neuer ADR Pflicht (z.B. ADR-0004), der ADR-0001 supersedet:

- Konkreter Multi-User-Use-Case wird beauftragt (Klassenraum, Forschungsgruppe, SaaS-Beta).
- Public-Internet-Deployment wird beworben.
- Audit-Trail-Anforderung von außen (DSGVO bei Multi-User-Daten, Compliance-Reviews).
- Rollen/Permissions-Granularität wird im Frontend gefordert.

Default-Migrationspfad (laut ADR-0001 § Optionen): **Option B — HttpOnly-Session** mit Server-Side-Session-Store in Redis, `flask-login` und User-Tabelle in Neo4j/SQLite.

### Hardstops für v1.0

- Keine Public-Internet-Werbung für Agora bis zu einem v2-ADR mit echtem Auth-Modell.
- Keine Marketing-Aussagen wie „Multi-User-Simulator".
- Keine Reaktivierung von `?token=` in Prod (Hardstop ist code-verifiziert in `backend/app/utils/auth.py::_extract_token`).
- Keine Erweiterung des Tokens auf User-Identität ohne neuen ADR.
