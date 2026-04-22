# Security Hardening — Changelog und Migrations-Hinweise

**Stand:** 2026-04-22, Europe/Berlin
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
| `VISION_MAX_CALLS_PER_UPLOAD` | nein | `40` | Hartes Cap für Vision-LLM-Calls pro PDF-Upload. |

---

## Offene Punkte (nach Phase 3 abgearbeitet)

- Upstream-Review-Status aus `SECURITY_REVIEW_SUMMARY.md` ist durch diese Phasen teilweise überholt; der Abschnitt dort wird in einem Follow-up abgeglichen.
- Langfristig: echte Session-/Login-Auth statt Static-Token. Aktueller Ansatz ist ein Shared-Secret-Bearer, was für Single-User-Dev-Setups OK ist, aber kein Multi-User-Szenario abbildet.
