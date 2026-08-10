# Security Threat Model

**Stand:** 2026-05-01, Europe/Berlin
**Gegen den Code geprüft:** 2026-08-11 — Dateipfade, Kommandos, Skript- und Dokumentverweise. Die fachlichen Aussagen dieses Dokuments sind dabei **nicht** einzeln nachvollzogen worden.
**Scope:** Single-User-Agora hinter Loopback / Tailscale, mit optionalem
Reverse-Proxy. Kein Mehrbenutzer-AuthN/AuthZ-Stack. Das Modell deckt
Application-Layer-Angriffe auf den lokalen Stack und Drive-by-Vektoren
gegen den Browser des einen Users — **nicht** Nation-State-grade Attacker
oder physischen Zugriff auf die Maschine.

Verwandte Dokumente:
- [`auth.md`](auth.md) — Token-Vertrag und Frontend-Storage-Modi.
- [`security-hardening.md`](security-hardening.md) — Phase 1/2/3 plus P1
  CI-Security-Scans, Slice 3 Redis-Tickets.
- [`dependency-risk-register.md`](dependency-risk-register.md) — aktive
  CVE-Baseline und Aufräum-Prozess.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Hardening-Pflicht
  in Produktion.

---

## Assets

| Asset | Sensitivität | Wo lebt es | Warum schützenswert |
|---|---|---|---|
| **Neo4j-Daten** (Wissensgraphen, Episoden, Embeddings) | hoch | Compose-Volume `neo4j_data` | Inhaltliche Substanz aller Reports; ein Angreifer mit Schreibrecht kann Reports beliebig vergiften. |
| **Uploads** (PDF/MD/TXT) | mittel-hoch | Bind-Mount `./backend/uploads` | Quellmaterial inkl. evtl. interner Dokumente; Path-Traversal oder Prompt-Injection beginnt hier. |
| **Reports** + Audit-Trails | mittel | `./backend/reports/`, Storage über `ArtifactStore` | Endprodukt der Pipeline; Manipulation untergräbt das Vertrauen ins System. |
| **OASIS-Artefakte** (`simulation_config.json`, `state.json`, Persona-CSV, Subprocess-Logs) | mittel | Bind-Mount `./backend/uploads/<sim_id>/` | Persistierte Persona-Felder werden vom OASIS-Subprozess in System-Prompts gespiegelt — Prompt-Injection-Surface. |
| **Auth-Token** (`AGORA_AUTH_TOKEN`) | hoch | `.env` auf Host, Frontend-`localStorage` oder JS-Heap | Single shared secret; Leak öffnet die gesamte API. |
| **SSE-/Download-Tickets** (`v1.<exp>.<scope>.<sig>`) | mittel | URL-Parameter, Redis (`ticket:<sig>`), in-process-Set als Fallback | Zeitlich begrenzt + scope-bound, aber während der Lebenszeit voll-mächtig im Scope. |
| **`SECRET_KEY`** | hoch | `.env` | Signiert `itsdangerous`-Tickets und Flask-Session-Cookies. |
| **Neo4j-Passwort** | hoch | `.env`, an Compose-Service `neo4j` durchgereicht | DB-Auth; Bolt-Treiber im Backend kennt den Wert. |
| **HuggingFace-Cache** + lokale Modelle | niedrig | `./backend/.cache/huggingface` | Re-fetch ist kostenlos, aber 1+ GB Bandbreite und Cold-Start-Risiko. |
| **`backend/agora.log`** | niedrig-mittel | tmpfs `/app/backend/logs` (Container) bzw. Bind-Mount lokal | Enthält Auth-Mode, Konfigurationsfehler; Logger-Redaction blendet Token, aber Restleck-Pfade bleiben möglich. |

---

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Internet  /  Tailnet  /  LAN                                           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  TLS / Tailscale
                       ┌───────▼────────┐
                       │ Reverse-Proxy  │  ◄── B0  Boundary 0: TLS-Term, RateLimit
                       │ (Traefik/Nginx)│
                       └───────┬────────┘
                               │ HTTP/1.1, X-Forwarded-*
              ┌────────────────▼─────────────────┐
              │       Browser (User)             │  ◄── B1  Boundary 1: Browser ↔ Frontend
              │  Vue 3 SPA, JS-Heap-Token        │
              └────────────────┬─────────────────┘
                               │ fetch() + X-Agora-Token
              ┌────────────────▼─────────────────┐
              │       Flask Backend (Gunicorn)   │  ◄── B2  Boundary 2: Frontend ↔ Backend
              │  Token-Guard, CORS-Whitelist,    │
              │  signed_ticket, install_blueprint│
              └──┬───────┬──────────┬────────────┘
                 │       │          │
       Bolt 7687 │  6379 │     11434│        ◄── B3  Boundary 3: Backend ↔ Internals
                 ▼       ▼          ▼
          ┌──────────┐ ┌──────┐ ┌─────────┐
          │  Neo4j   │ │Redis │ │ Ollama  │
          └──────────┘ └──────┘ └─────────┘
                               │
                 OASIS-Subprozess (eigener Python-Prozess)  ◄── B4  Boundary 4
                               │
                               ▼
                       ┌──────────────────┐
                       │ Outbound HTTP    │  ◄── B5  Boundary 5: Backend ↔ Internet
                       │ (Tavily, fetch_url)
                       └──────────────────┘
```

| Boundary | Vom → Ins | Kontrolle |
|---|---|---|
| **B0** Reverse-Proxy ↔ Backend | Internet/Tailnet → Loopback | TLS, Rate-Limit, Header-Hardening, `client_max_body_size`. Backend bindet auf `127.0.0.1:5001`. |
| **B1** Browser ↔ Frontend | Untrusted Browser-Renderer → Vue-SPA | Vue-Default-HTML-Escape, eigener Markdown-Sanitizer (`frontend/src/utils/markdown.ts`), keine `v-html` ohne Sanitize, Token in JS-Heap (Memory-Mode) statt `localStorage`. |
| **B2** Frontend ↔ Backend | Browser-fetch → Flask | `install_blueprint_guard()` auf jedem `/api/*`-Blueprint, `token_required` Decorator, CORS-Whitelist (Loopback + `AGORA_EXTRA_ORIGINS`), Tickets für SSE/Download-Pfade. |
| **B3** Backend ↔ Neo4j/Redis/Ollama | Backend → Internal-Service | Compose-Netzwerk, kein Host-Port-Publishing in Prod-Override. Neo4j-Auth, Redis ohne Auth (Compose-intern), Ollama ohne Auth (Loopback-only). |
| **B4** Backend ↔ OASIS-Subprozess | Flask-Prozess → fork/exec Python | IPC über File + Redis-Bus (`subprocess_redis_bridge.py`). Persona-Felder werden in Subprozess-System-Prompts gespiegelt — Whitelist-Filter beim `POST /<sim>/profiles`-Merge. |
| **B5** Backend ↔ Outbound HTTP | Flask → Internet | SSRF-Blocker (`web_tools._is_public_url`), Request-Timeouts, Vision-Call-Cap (`VISION_MAX_CALLS_PER_UPLOAD`). |

---

## Angreifer-Modelle

### A1 — Untrusted LAN / Tailnet-Peer

**Kontext:** Agora läuft auf einer Maschine im Tailnet oder hinter einem
Reverse-Proxy. Ein anderer Tailnet-Peer (oder ein LAN-Co-Tenant) kann den
Stack TCP-erreichen.

**Was er versucht:**
- `/api/graph/project/<id>` `DELETE` ohne Auth.
- CORS-Preflight von beliebigem Origin, dann Cross-Origin-`fetch()` aus
  Drive-by-Browser auf einem anderen Tailnet-Host.
- Brute-Force-Bearer-Tokens (timing-Side-Channel).

**Aktive Mitigations:**
- Loopback-Bind aller Compose-Ports (Default-Compose `127.0.0.1`),
  Prod-Override droppt zusätzlich Vite + Neo4j-Host-Ports.
- `install_blueprint_guard()` auf allen `/api/*`-Blueprints; `/health`
  bleibt bewusst öffentlich.
- CORS-Whitelist: nur statische Defaults plus `AGORA_EXTRA_ORIGINS`. Kein
  Wildcard, außer `AGORA_CORS_ALLOW_ALL=true` mit Log-Warning (in Prod
  hard rejected, siehe [`deployment-prod-like.md`](deployment-prod-like.md)).
- Token-Vergleich timing-safe (`hmac.compare_digest`).

**Restrisiko:** Wer den Reverse-Proxy umgeht und den `127.0.0.1:5001`
direkt erreicht (gleicher Host als Co-Tenant), umgeht TLS und
Rate-Limit. Mitigation = Container-Isolation und Single-Tenant-Host.

### A2 — XSS-Gadget oder kompromittiertes Browser-Plugin

**Kontext:** Der User hat ein Browser-Tab mit Agora offen. Eine andere
Site oder ein Plugin landet im selben Browser.

**Was er versucht:**
- `localStorage.getItem('agora_token')` aus dem Agora-Origin (XSS-Origin
  oder via manipuliertes Plugin mit `host_permissions`).
- Daten-Exfiltration über `fetch()` aus dem Agora-Origin (gleicher Origin
  → Token wird automatisch angehängt).
- DOM-Injection in `v-html`-Pfaden, vor allem in Report-Markdown.

**Aktive Mitigations:**
- Memory-Mode (`VITE_AGORA_TOKEN_STORAGE=memory`) als Prod-Empfehlung —
  Token überlebt keinen Page-Reload.
- Markdown-Sanitizer (`frontend/src/utils/markdown.ts`, 9 Regression-Tests
  seit v0.9.0) blockt aktive XSS-Vektoren in Report-Inhalten.
- CORS-Whitelist verhindert Cross-Origin-Aufrufe aus fremden Tabs.

**Restrisiko:** Aktiver XSS-Exploit im selben Tab kann während der
Session den Token aus dem JS-Heap lesen — Memory-Mode reduziert das
Residuum, eliminiert den Vektor aber nicht. Echte Mitigation =
HttpOnly-Cookie-Flow (in [`auth.md`](auth.md), Option C, als
Zielarchitektur dokumentiert; aktuell nicht implementiert).

### A3 — Supply-Chain / kompromittierte Dependency

**Kontext:** Eine NPM- oder PyPI-Dependency wird upstream kompromittiert
(typo-squat, hijacked maintainer, malicious version).

**Was er versucht:**
- Build-Time-Hook im Frontend (`postinstall`) liest `.env`.
- Import-Time-Code im Backend macht Outbound-Call mit Secrets.
- Tool-Call durch ein malicious package während `pytest` oder
  `vite build`.

**Aktive Mitigations:**
- `bun audit --audit-level=high` und `pip-audit` als CI-Gates (siehe
  [`security-hardening.md`](security-hardening.md), P1-Sektion).
- Gitleaks-Scan in CI mit historischer Baseline (`.gitleaksignore`,
  fingerprint-genau).
- Dependency-Risk-Register
  ([`dependency-risk-register.md`](dependency-risk-register.md)) trackt
  bewusst ignorierte CVEs mit Owner, Frist und Issue-Link; alle 30 Tage
  Review.
- Lockfiles versioniert (`bun.lock` in Root und `frontend/`, `backend/uv.lock`).

**Restrisiko:** Ein neues Advisory kann mehrere Tage zwischen Disclosure
und CI-Detection liegen. CI deckt **bekannte** Findings, nicht
Zero-Day-Lieferketten-Hijacks. Mitigation = niedrige Dependency-Anzahl,
explizite Pins, Supply-Chain-Disziplin (kein blindes `bun install` ohne
`--frozen-lockfile` aus
Forks).

### A4 — Geleakter `AGORA_AUTH_TOKEN`

**Kontext:** Der Token landet in einem Screenshot, einem Pastebin, einem
Browser-History-Export oder einem fehlerhaft geteilten Setup-Snippet.

**Was er versucht:**
- API-Calls von außerhalb des erlaubten Tailnets gegen die Reverse-Proxy-
  URL.
- Persona-Manipulation (`POST /<sim>/profiles`) zur Prompt-Injection.
- Datenexfiltration über `GET /api/graph/data/<id>`.

**Aktive Mitigations:**
- Token ist case-sensitive `secrets.token_urlsafe(32)`-Niveau, nicht in
  `.env.example` als Default.
- Rotation = `.env` ändern + Container-Restart + Frontend-`localStorage`/
  Memory-Token neu setzen. Manuell, aber unkompliziert.
- `AGORA_AUTH_TOKEN` nicht in Logs (Logger-Redaction-Tests im Backend).
- Reverse-Proxy ist die externe Angriffsfläche; Tailscale-only stellt
  sicher, dass der Token-Klau außerhalb des Tailnets nicht reicht.

**Restrisiko:** Keine automatische Rotation, keine Audit-Trail-Pflicht
für ausgehende API-Calls. Alle Token-Träger sind gleichermaßen voll
berechtigt — kein Rollenmodell.

### A5 — Bösartiges Upload-Dokument

**Kontext:** PDF/MD-Datei mit präparierten Inhalten landet im Upload-Pfad.

**Was er versucht:**
- Path-Traversal über manipulierten Filename (`../../etc/passwd`).
- Cypher-Injection über LLM-extrahierte Entity-Types mit Backticks.
- Prompt-Injection im Content („Ignoriere alle Regeln…“).
- Vision-Cost-Explosion durch hunderte eingebettete Bilder.

**Aktive Mitigations:**
- `Config.ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}`,
  `MAX_CONTENT_LENGTH = 50 MB`.
- Cypher-Label-Sanitizer (`backend/app/storage/neo4j_mappings.py`,
  Regex `^[A-Za-z_][A-Za-z0-9_]{0,49}$`, Backtick-Neutralization).
- Vision-Call-Cap (`VISION_MAX_CALLS_PER_UPLOAD`, Default 40, hardes
  Cap mit einmaligem Warning-Log).
- Persona-Whitelist auf `POST /<sim>/profiles` reduziert die in
  Subprozess-Prompts spiegelbaren Felder auf bekannte Schlüssel.

**Restrisiko:** Prompt-Injection im **Inhalt** des Uploads bleibt — das
LLM verarbeitet User-Content und kann durch geschicktes Wording
umkonditioniert werden. Test-Coverage für SSRF, Upload-Limits und
Cypher-Sanitizer ist umgesetzt (`backend/tests/test_ssrf_blocker.py`,
`test_upload_limits.py`, `test_cypher_label_sanitizer.py`); der zugehörige
Plan liegt nicht mehr im Repository.

### A6 — Ungewollt erreichbare interne Ressource (SSRF)

**Kontext:** ReportAgent-Tool `fetch_url` wird mit einer URL aufgerufen,
die auf eine interne Ressource zielt (`localhost`, `169.254.169.254`,
`10.0.0.x`).

**Aktive Mitigations:**
- `_is_public_url()` macht DNS-Lookup, prüft `is_private`,
  `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`,
  `is_unspecified` und blacklisted explizit AWS-/EC2-Metadaten-IPs
  (`169.254.169.254`, `fd00:ec2::254`).
- Reject-Reason wird geloggt; `fetch_url` erlaubt nur `http`/`https`.

**Restrisiko:** DNS-Rebinding zwischen Lookup und tatsächlichem Request
ist nicht abgedeckt — Tavily macht den eigentlichen Outbound-Call,
unsere Pre-Check-IP ist eine zweite Auflösung. Im aktuellen Architekturpfad
(`fetch_url` → Tavily) ist das Risiko niedrig, weil Tavily extern fetched.
Bei einem zukünftigen Direkt-Fetch-Pfad muss das Modell neu bewertet werden.

---

## Bekannte Restrisiken (Top 5)

1. **Kein echtes AuthN/AuthZ.** `AGORA_AUTH_TOKEN` ist ein Shared-Secret-
   Bearer; alle Token-Träger sind voll berechtigt. Es gibt kein
   Login-Backend, keine Sessions, keine Rollen, kein RBAC. Single-User-
   Vertrauensmodell ist die Grundannahme. Zielarchitektur:
   `/api/auth/login` mit HttpOnly-Cookie + Session-Backend (siehe
   [`auth.md`](auth.md), Option C). Status: nicht implementiert.

2. **Keine Secrets-Rotation.** `SECRET_KEY`, `AGORA_AUTH_TOKEN`,
   `NEO4J_PASSWORD` werden manuell gesetzt und manuell rotiert. Keine
   Vault-Integration, kein Refresh-Flow, keine Ablaufzeit. Ein Leak
   bleibt gültig bis zur nächsten manuellen Rotation.

3. **OASIS-Subprozess-Vertrauen.** Persona-Felder fließen in
   Subprozess-System-Prompts; der Subprozess ist genauso vertrauenswürdig
   wie der Flask-Parent (gleicher User, gleicher FS-Zugriff). Whitelist-
   Filter in `simulation_profiles.py` reduziert die Felder, aber ein
   manipuliertes Persona-Dataset kann das Agenten-Verhalten weiterhin
   beeinflussen — das ist Feature, nicht Bug, aber damit auch Angriffsfläche.

4. **Prompt-Injection im Quelldokument.** Upload-Content fließt durch
   NER, Embedding, ReportAgent. Ein Dokument mit „Ignoriere alle
   Regeln…“ kann das Verhalten des LLM-Pfades beeinflussen — strukturelle
   Mitigation (Output-Validation, Tool-Call-Whitelist) ist nur teilweise
   implementiert. Tool-Call-Limit (`MAX_TOOL_CALLS_PER_ACTION`) und
   Tool-Schema-Trennung (Issue #47) reduzieren die Hebelwirkung.

5. **Browser-Token-Storage.** `localStorage` ist der Dev-Default; ein
   einmaliger XSS-Treffer reicht zum Token-Theft. Memory-Mode reduziert
   das Residuum, aber ein aktiver Exploit im selben Tab ist nicht
   ausgeschlossen. HttpOnly-Cookie ist die saubere Lösung — siehe
   Restrisiko #1.

---

## Was bewusst out-of-scope ist

- **Multi-Tenant-Setups.** Agora ist Single-User. Wer das Ding für
  mehrere Personen aufstellt, baut zwingend eigene Auth davor.
- **Container-Escape und Kernel-Exploits.** Wir setzen auf
  read-only-Rootfs, `cap_drop: ALL`, `no-new-privileges`. Tiefere
  Container-Härtung (gVisor, Seccomp-Profile, Falco) ist nicht aktiviert
  und auch nicht geplant.
- **Physischer Zugriff auf den Host.** Wer am Server sitzt, hat
  `.env` im Klartext, das Neo4j-Volume, die Uploads. Encryption-at-rest
  liegt außerhalb des Scopes.
- **DDoS / Volumen-Angriffe.** Rate-Limiting im Reverse-Proxy ist
  Pflicht für jedes Internet-exponierte Setup; Backend selbst hat
  keinen eingebauten Limiter.
- **Browser-Hijack-Schutz auf OS-Ebene.** Ein kompromittiertes OS
  (Keylogger, Disk-Inspector) hebelt jede Browser-Maßnahme aus.

---

## Mapping zu umgesetzten Mitigations

| Threat | Slice / Phase | Datei |
|---|---|---|
| Wildcard-CORS, fehlender Auth-Token | Phase 2 (v0.6.0+) | `backend/app/__init__.py`, `backend/app/utils/auth.py` |
| Bekannte Platzhalter-Secrets | Slice 1 PR1 | `backend/app/config.py`, `backend/tests/test_config_security.py` |
| Multi-Worker-Replay auf SSE-Tickets | Slice 3 PR3 | `backend/app/utils/signed_ticket.py`, `backend/tests/test_signed_ticket_redis.py` |
| Aktive CVEs ohne Exit-Plan | Slice 4 PR4 | [`dependency-risk-register.md`](dependency-risk-register.md), `.github/workflows/ci.yml` |
| `localStorage`-Token + XSS-Residuum | Slice 5 PR5 | `frontend/src/api/index.ts`, [`auth.md`](auth.md) |
| SSRF auf interne IPs | Phase 3.1 | `backend/app/services/web_tools.py` |
| Prompt-Injection über Persona-Merge | Phase 3.2 | `backend/app/api/simulation_profiles.py` |
| Vision-Cost-Explosion | Phase 3.3 | `backend/app/utils/file_parser.py` |
| Cypher-Label-Injection | Phase 3.4 / Issue #50 | `backend/app/storage/neo4j_mappings.py` |
| Compose Dev/Prod-Drift, offene Ports | Slice 2 PR2 | `docker-compose.yml`, `docker-compose.prod.yml` |

---

## Review-Pflichten

- **Code-Änderung an einer Trust Boundary** → diesen Threat-Model-Eintrag
  prüfen und ggf. aktualisieren. Boundaries sind B0–B5 oben.
- **Neue Outbound-HTTP-Quelle** → SSRF-Blocker erweitern
  (`_is_public_url` ist die einzige Wahrheit), Modell-Eintrag A6 anfassen.
- **Neuer Persistenzpfad für Secrets** → Asset-Tabelle ergänzen,
  Rotation/Backup-Implikationen klären.
- **Neue Dependency** → CVE-Baseline und `dependency-risk-register.md`
  prüfen, A3 ggf. nachschärfen.
- **Größere Schema-Änderung an `/api/*`** → Auth-Decorator-Coverage
  testen; B2-Boundary darf keine Lücke bekommen.
