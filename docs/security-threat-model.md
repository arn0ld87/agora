# Security Threat Model

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Single-User-Agora auf lokalem Host, Tailnet oder hinter einem gehärteten Reverse-Proxy. Kein Multi-Tenant-/Enterprise-IAM-Modell.

Verwandte Referenzen:

- [`auth.md`](auth.md)
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md)
- [`security-hardening.md`](security-hardening.md)
- [`dependency-risk-register.md`](dependency-risk-register.md)
- [`deployment-prod-like.md`](deployment-prod-like.md)
- [`STATUS.md`](STATUS.md)

---

## 1. Sicherheitsziel

Agora soll im definierten Single-User-Betrieb verhindern, dass:

- unauthentifizierte oder unzureichend berechtigte Clients sensible API-Aktionen ausführen,
- Secrets über Logs, Reports, Manifeste oder Frontend-Persistenz unnötig offengelegt werden,
- manipulierte Uploads oder Modellinhalte direkt zu Code-/Filesystem-/Netzwerkzugriff eskalieren,
- ein Fehler in Evidence-/Statusverträgen als scheinbar vertrauenswürdiger Erfolg ausgeliefert wird,
- interne Dienste durch den Standard-Stack unbeabsichtigt öffentlich erreichbar werden.

Das Modell garantiert **nicht**, dass synthetische Personas korrektes reales Verhalten abbilden. Simulationstreue ist ein Trust-/Produktproblem, nicht allein ein klassischer Security-Guard.

---

## 2. Assets

| Asset | Sensitivität | Persistenz / Ort | Risiko |
|---|---|---|---|
| Quelldokumente | hoch | `backend/uploads/` | können interne oder personenbezogene Inhalte enthalten |
| Knowledge Graph / Embeddings | hoch | Neo4j | Manipulation vergiftet Retrieval und Reports |
| Simulationsartefakte | mittel-hoch | `backend/uploads/simulations/<sim_id>/` | enthalten Personas, Config, Aktionen und Logs |
| Reports / Evidence / Audit | mittel-hoch | `backend/uploads/reports/<report_id>/` | Endprodukt; falsche Integrität erzeugt falsches Vertrauen |
| `AGORA_AUTH_TOKEN` | kritisch | Laufzeit/.env | Master-API-Zugriff |
| Workspace-API-Keys | hoch | verschlüsselt in `backend/data/api_keys.json` | technische Scoped-Credentials |
| `AGORA_FERNET_KEY` | kritisch | Laufzeit/.env | entschlüsselt Workspace-API-Key-Store |
| Provider-Credentials | kritisch | verschlüsselt in `backend/data/llm_provider_secrets.json` | Zugriff auf externe LLM-/Embedding-Dienste |
| `AGORA_SECRET_KEY` | kritisch | Laufzeit/.env | entschlüsselt Provider-Secret-Store |
| `SECRET_KEY` | kritisch | Laufzeit/.env | signiert Tickets/Flask-Daten |
| Neo4j-Credentials | kritisch | Laufzeit/.env | direkter Datenbankzugriff |
| Redis-State | mittel | Redis | Live-State, Events, Ticket-/IPC-Funktionen; keine dauerhafte Job-SSoT |
| CI-/Release-Artefakte | mittel-hoch | GitHub Actions/GHCR | Supply-Chain- und Release-Integrität |

---

## 3. Trust Boundaries

```text
Browser / API Client
        │
        │ TLS / Tailnet / Loopback
        ▼
Reverse Proxy (optional)
        │
        ▼
Flask API + Auth/Scopes
   │       │        │
   │       │        ├────────► HTTP LLM/Embedding Provider
   │       │
   │       ├───────────────► CLI Provider Subprocess (z. B. Codex CLI)
   │
   ├────────► Neo4j
   ├────────► Redis
   ├────────► Filesystem-Artefakte
   │
   └────────► OASIS/CAMEL Subprocess
                │
                └──────────► Provider/Model Runtime
```

### B0 — Netzwerk / Reverse Proxy

Kontrollen:

- Standard-Prod-Bind auf Loopback,
- TLS/VPN/Reverse-Proxy für Remote-Zugriff,
- ProxyFix nur explizit konfigurieren,
- keine Annahme, dass ein zufälliger LAN-/Tailnet-Peer vertrauenswürdig ist.

### B1 — Browser/API-Client → Flask

Kontrollen:

- `AGORA_AUTH_TOKEN` als Master-Credential,
- Workspace-API-Keys mit Scopes,
- signierte Tickets für URL-Auth,
- CORS-Whitelist/konfigurierte Origins,
- strukturierte API-Fehler statt roher Exceptions.

### B2 — Flask → persistente Daten

Kontrollen:

- sichere Pfadauflösung/definierte Roots,
- atomare Writes für kritische Artefakte,
- verschlüsselte Secret-/API-Key-Stores,
- Neo4j-Auth und getrennte Storage-Schicht.

### B3 — Flask → OASIS/CAMEL-Subprozess

Der Simulationsprozess ist eine **Prozessgrenze, keine Sicherheits-Sandbox**. Er läuft unter demselben Vertrauenskontext des Deployments und besitzt bewusst Zugriff auf benötigte Artefakte/Runtime-Verbindungen.

Die Environment-Weitergabe ist whitelist-basiert; Secrets sollen nicht pauschal per `os.environ.copy()` an jeden Subprozess vererbt werden.

### B4 — Flask → CLI-Provider

`codex_cli` startet einen lokal authentifizierten CLI-Prozess. Seine Auth lebt in der lokalen CLI-Session, nicht im Agora-Provider-Secret-Store.

Risiken:

- der CLI-Prozess besitzt Rechte des Backend-Users,
- Prompts sind untrusted Daten,
- große Eingaben müssen über stdin statt unsichere/limitierte argv-Übergabe laufen,
- CLI-Transport ist keine Sandbox gegen einen kompromittierten lokalen Useraccount.

### B5 — Backend → externe Provider / Web

Kontrollen:

- Transport-Security für credential-behaftete HTTP-Endpunkte,
- Timeouts/Retry-Grenzen,
- Budget-Limits,
- SSRF-Prüfung für direkte URL-Werkzeuge,
- Secret-Redaction in Logs.

---

## 4. Angreifermodelle

### A1 — Untrusted LAN/Tailnet-Peer

**Ziel:** API ohne Credential nutzen, Ressourcen lesen/löschen, LLM-Kosten auslösen.

**Mitigations:**

- Loopback-orientierte Produktionsdefaults,
- Auth-Guard auf `/api/*`,
- Master-Token oder scoped API-Key,
- Reverse-Proxy/Tailnet als zusätzliche Netzgrenze.

**Restrisiko:** Ein korrektes Master-Token besitzt administrative Wirkung. Netzwerkisolation ersetzt daher keine Credential-Hygiene.

### A2 — Geleakter Master-Token / API-Key

**Ziel:** API-Funktionen im erlaubten Umfang ausführen.

**Mitigations:**

- Workspace-API-Keys können minimierte Scopes tragen und widerrufen werden.
- Master-Token wird timing-safe verglichen.
- Query-Bearer `?token=` ist in Produktion deaktiviert.
- URL-Auth verwendet kurzlebige signierte Tickets.

**Restrisiko:** Master-Token = Admin. Es existiert noch kein Benutzer-/Session-/RBAC-Modell.

### A3 — XSS / kompromittierter Browserkontext

**Ziel:** Client-seitige Tokens lesen oder API-Aufrufe im Namen des Users ausführen.

**Mitigations:**

- Vue escaped normalen Text standardmäßig,
- Report-/Markdown-Pfade müssen sanitizen,
- persistenter Token-Storage ist vermeidbar/reduzierbar,
- CORS verhindert keinen XSS im eigenen Origin, begrenzt aber fremde Origins.

**Restrisiko:** Ein Credential im JS-Kontext ist bei erfolgreicher Same-Origin-XSS angreifbar. Ein vollständiger HttpOnly-Session-Login existiert derzeit nicht.

### A4 — Bösartiges Quelldokument / Prompt Injection

**Ziel:** Modellinstruktionen über Upload, Graphinhalt oder Observation beeinflussen.

Beispiele:

- „Ignoriere Systemregeln …“ im Quelldokument,
- manipulierte Persona-Felder,
- untrusted Observation aus Simulationsaktionen,
- externe Webinhalte mit instruktionsähnlichem Text.

**Mitigations:**

- Schema-/Output-Validierung,
- Tool-Whitelists und Limits,
- Trennung zwischen Quellinhalt und Systeminstruktion,
- Sanitizer/Validatoren auf strukturierten Übergängen,
- Evidence-Gates statt blindem Vertrauen in Modellprosa.

**Offen:** #1224 verfolgt zusätzliche Prompt-Injection-Härtung von Simulation-Observation. Diese Grenze ist nicht „gelöst“, nur weil JSON-Schemas existieren.

### A5 — Path Traversal / Dateimanipulation

**Ziel:** Upload-/Reportpfade verlassen oder fremde Artefakte überschreiben.

**Mitigations:**

- definierte Upload-/Data-Roots,
- ID-/Pfadvalidierung,
- sichere Join-/ArtifactStore-Logik,
- atomare Writes,
- read-only Root-Filesystem im gehärteten Container mit expliziten Write-Pfaden.

### A6 — Graph-/Cypher-Manipulation

**Ziel:** dynamische Labels/Relationen zur Cypher-Injection oder Datenvergiftung verwenden.

**Mitigations:**

- Label-/Identifier-Sanitizing,
- Storage-Adapter statt frei zusammengebauter Queries in API-Routen,
- idempotente UUID-basierte Writes für retry-kritische Graphobjekte (#1460).

### A7 — SSRF / interne Netzressourcen

**Ziel:** Web-/Research-Tools gegen Loopback, RFC1918, Link-Local oder Metadata-Endpunkte richten.

**Mitigations:**

- URL-/IP-Prüfung vor direkten Fetch-Pfaden,
- nur definierte Schemes,
- Timeouts,
- keine automatische Gleichsetzung „URL vom Modell = vertrauenswürdiges Ziel“.

Bei neuen direkten Outbound-Fetchern muss die SSRF-Prüfung erneut bewertet werden; ein Precheck ist insbesondere bei DNS-Rebinding nicht automatisch ausreichend.

### A8 — Supply Chain

**Ziel:** kompromittierte NPM-/PyPI-/Action-Abhängigkeit in Build/Test/Runtime ausnutzen.

**Mitigations:**

- Lockfiles,
- Dependency-/Secret-Scanning,
- SBOM-Workflow,
- `dependency-risk-register.md` mit Owner/Deadline/Hardstop,
- Release-Publish erst nach definierten Gates.

**Restrisiko:** Scans erkennen bekannte Probleme, keine garantierte Zero-Day-Freiheit.

### A9 — Ciphertext ohne passenden Master-Key

**Ziel/Folge:** nicht klassische Angreiferaktion, aber relevanter Availability-/Recovery-Failure.

Zwei getrennte kritische Paare:

```text
AGORA_SECRET_KEY + llm_provider_secrets.json
AGORA_FERNET_KEY + api_keys.json
```

Ein Restore des Ciphertexts ohne passenden Master-Key bedeutet Datenverlust der gespeicherten Credentials.

Mitigation: getrennt gesicherte Master-Keys + Restore-Drills.

---

## 5. Evidence-/Trust-Risiken

Nicht jedes Trust-Problem ist ein Angreiferproblem. Für Agora sind folgende fachliche Integritätsrisiken relevant:

### Evidence passt nicht zum Claim

- Quantoren können stärker sein als die aggregierte Evidence (#1345).
- Eval-Seeds können erwartete Antworten enthalten und als vermeintliche Erkenntnis wieder auftauchen (#1240).

### Role Leakage

Synthetische Personas können Rollen wechseln oder fremde Fachperspektiven annehmen (#1323). Das kann einen Report inhaltlich vergiften, ohne dass irgendein externer Angreifer beteiligt ist.

### Recommender-Reproduzierbarkeit

Der Twitter-Recommender besitzt bekannte Modell-/Pooler-Probleme (#1236). Dadurch kann Rankingvarianz wie „soziales Verhalten“ aussehen, obwohl sie aus der technischen Empfehlungsschicht stammt.

### Reproduzierbarkeit

Ein gespeicherter Seed allein kontrolliert noch nicht alle Zufalls-/Modell-/Promptquellen (#763/#1274). Deshalb darf Reproduzierbarkeit nicht als Security-/Audit-Eigenschaft behauptet werden, bevor der vollständige Manifest-/Replay-Vertrag steht.

---

## 6. Aktive technische Mitigations

| Bereich | Aktueller Schutz |
|---|---|
| API Auth | Master-Token + Workspace-API-Keys |
| Authorization | Scopes auf dafür geschützten Endpunkten |
| URL Auth | signierte kurzlebige Tickets |
| Provider-Secrets | Fernet-Store mit `AGORA_SECRET_KEY` |
| Workspace-API-Key-Store | Fernet-Store mit `AGORA_FERNET_KEY` |
| Subprozess-Env | Allowlist statt Vollvererbung |
| Container | read-only Rootfs / `cap_drop` / explizite Write-Pfade im Prod-Override |
| Contracts | Pydantic + JSON-Schema + Zod-Drift-Gates |
| Evidence | Contract-Gates und `evidence_omitted` bei invalidem Altbestand |
| Logs | strukturierte Logger + Secret-Redaction |
| Dependencies | Audit-/Risk-Register-/SBOM-Gates |
| Run-Kosten | Call-/Token-/Kosten-/Zeitbudgets |

---

## 7. Bekannte Restrisiken vor 1.0

1. **Shared Admin-Token:** kein Human-IAM/RBAC; Master-Token bleibt Vollzugriff.
2. **Prompt Injection:** untrusted Quellen/Observation sind noch nicht überall maximal getrennt (#1224).
3. **Webprozess-Langläufer:** Prepare/Report/Graph sind noch nicht vollständig restart-sicher (#1472).
4. **Embedding-SSoT:** UI-aktive Konfiguration kann von Runtime-Env abweichen (#1417).
5. **Simulationstreue:** Role Leakage/Recommender-Probleme (#1323/#1236).
6. **Reproduzierbarkeit:** Manifest/Replay unvollständig (#763/#1274).
7. **Restore-Nachweis:** Backup-Doku existiert, vollständiger Fresh-Host-Drill bleibt Release-Arbeit (#766).

---

## 8. Out of Scope

Für `0.9.5` bewusst nicht versprochen:

- Multi-Tenant-Isolation,
- Enterprise-SSO/RBAC,
- Schutz gegen kompromittierten Host/Kernel/Root,
- Hardware-backed Secret Storage,
- DDoS-Schutz ohne vorgelagerten Proxy/Netzlayer,
- wissenschaftliche Validität synthetischer Verhaltensprognosen.

---

## 9. Review-Pflichten

Dieses Threat Model muss geprüft werden, wenn:

- eine neue Trust Boundary entsteht,
- neue Secrets oder Credential-Stores eingeführt werden,
- ein neuer Provider-/CLI-/Outbound-Transport hinzukommt,
- Upload-/Parsing-/Web-Tools verändert werden,
- Auth-/Scope-Regeln geändert werden,
- ein neuer persistenter Artefaktpfad entsteht,
- Container-/Netzwerk-Exposure geändert wird,
- Evidence-/Report-Gates abgeschwächt oder neu definiert werden.

Historische Security-Audits bleiben historische Belege. Der aktuelle Risk-Stand gehört hier, in [`STATUS.md`](STATUS.md), [`dependency-risk-register.md`](dependency-risk-register.md) und in offene Issues.
