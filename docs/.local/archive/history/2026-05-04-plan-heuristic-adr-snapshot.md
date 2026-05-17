# plan.heuristic.md — Architektur-Heuristiken (ADR-Snapshot 2026-05-04)

> **HISTORISCHER SNAPSHOT.** Dies ist der ADR-Drop vom 2026-05-04, der zusammen mit dem Backup-Master-Mapping aus `.git/agora-cleanup-backup-2026-05-04/plan.heuristic.md` in die offizielle [`docu/plan.heuristic.md`](../plan.heuristic.md) konsolidiert wurde. Aktueller verbindlicher Stand:
>
> - **Subagent-Routing pro Slice + ADR-Live-Register:** [`docu/plan.heuristic.md`](../plan.heuristic.md)
> - **Operative Findings & Maßnahmen:** [`PLAN.md`](../../PLAN.md)
> - **Test-Counts und Versionen:** [`docu/STATUS.md`](../STATUS.md)
>
> Diese Datei wird **nicht weiter gepflegt** — sie bleibt als Beleg für die ADR-Linie stehen, die am 2026-05-04 vorgeschlagen wurde.

---

**Stand:** 2026-05-04  
**Repo:** `arn0ld87/agora`  
**Status:** Audit-Snapshot. Konsolidiert in [`docu/plan.heuristic.md`](../plan.heuristic.md).

---

## 1. Zweck

Diese Datei ist die kompakte technische Gedächtnisstütze für zukünftige Slices.

Sie beantwortet:

- Welche Architekturentscheidungen gelten?
- Welche Code-Muster sind erwünscht?
- Welche Muster sind Warnsignale?
- Welche technischen Schulden sind aktiv?
- Welche Risiken brauchen Mitigation?

---

## 2. Architektur-Entscheidungen

### ADR-0001 — Local-first bleibt Kernprinzip

**Entscheidung:** Agora bleibt primär ein lokaler/Tailnet-Single-User-Simulator.

**Begründung:**

- LLM-/Embedding-/Graph-Workloads sind teuer, langsam und schwer multi-tenant-sicher.
- Lokale Ollama-/Neo4j-Setups passen zum ursprünglichen Use Case.
- Security-Baseline ist für private Netze deutlich realistischer als für Public SaaS.

**Konsequenz:**

- Public-Internet-Betrieb ist nicht Standard.
- README/SECURITY/Docker-Doku müssen klar sagen: kein öffentliches Mehrbenutzer-SaaS ohne zusätzliche AuthN/AuthZ, Rate-Limits und Abuse-Schutz.

---

### ADR-0002 — Flask + Vue + Neo4j + Ollama-kompatible Endpunkte

**Entscheidung:** Stack bleibt Flask/Python 3.11, Vue 3/Vite, Neo4j 5.x, OpenAI-kompatible LLM-Endpunkte.

**Begründung:**

- Backend ist service-orientiert genug für weitere Entkopplung.
- Neo4j passt zu GraphRAG und temporalen Beziehungen.
- OpenAI-kompatible APIs erlauben Ollama lokal und Cloud-Modelle.

**Konsequenz:**

- Keine Provider-Lock-ins.
- Provider-spezifische Sonderlogik muss isoliert bleiben.
- Embedding-Dimensionen müssen fail-fast validiert werden.

---

### ADR-0003 — Pydantic ist Backend-Contract-Quelle, Zod ist Frontend-Spiegel

**Entscheidung:** API-Verträge werden in Pydantic v2 modelliert und per JSON-Schema gespiegelt.

**Begründung:**

- Verhindert stille Contract-Drift zwischen Flask und Vue.
- Zod-Parsing macht Frontend-Fehler sichtbar statt nur hübsch kaputt.
- Schema-Drift-CI ist bereits vorhanden.

**Heuristik:**

- Neue API-Struktur = zuerst Pydantic-Modell.
- Keine Inline-JSON-Schemas.
- Frontend-Zod immer aus Backend-Contract ableiten oder bewusst spiegeln.
- `extra="forbid"` für API-Verträge.

---

### ADR-0004 — URL-bound Auth nur über kurzlebige signed tickets

**Entscheidung:** EventSource/Download-URLs dürfen keine long-lived Bearer-Tokens nutzen.

**Begründung:**

- `EventSource` kann keine Custom Header.
- `?token=` landet in Proxy-Logs, Browser-History und Referern.
- Signed tickets sind kurzlebig und scope-bound.

**Konsequenz:**

- SSE nutzt `POST /api/auth/ticket` + `?ticket=`.
- Backend blockt `?token=` im Non-Debug-Betrieb.
- Neue URL-basierte Endpunkte müssen `allow_ticket_auth()` verwenden.

---

### ADR-0005 — Prod läuft über Gunicorn gevent + optionalen nginx-Sidecar

**Entscheidung:** Prod-Target nutzt Gunicorn mit gevent; öffentlich erreichbare Topologie läuft über Reverse-Proxy.

**Begründung:**

- SSE/Long-Requests passen schlecht zu sync-Workern.
- nginx kann statische Assets, Healthchecks und SSE-Proxying sauber trennen.
- Backend-Port soll nicht direkt im Netz hängen.

**Konsequenz:**

- CI muss den kompletten Prod-Stack smoken.
- nginx-Konfiguration ist Teil des Produkts, nicht Betreiber-Folklore.
- Proxy-Timeouts und `proxy_buffering off` sind Pflicht für SSE.

---

### ADR-0006 — Redis Eventbus bevorzugt, File-Fallback bleibt

**Entscheidung:** Redis ist Compose-Default; File-Polling bleibt Offline-Fallback.

**Begründung:**

- Redis ist besser für Live-Events und SSE.
- File-Fallback hält lokale/kaputte Setups lauffähig.
- OASIS-Subprozess braucht robuste IPC.

**Konsequenz:**

- Eventbus-Zugriff nur über Abstraktion.
- Kein direkter Redis-Code in API-Routen.
- Fallback-Verhalten muss getestet bleiben.

---

### ADR-0007 — Config fail-fast statt kaputter Runtime

**Entscheidung:** Fehlende Secrets, falsche Embedding-Dimensionen und fehlende Auth im Non-Debug-Betrieb stoppen den Start.

**Begründung:**

- Späte Fehler in LLM-/Graph-Pipelines kosten Minuten und Nerven.
- Offene API durch vergessenes Token ist kein „Feature“, sondern ein Unfall mit Webserver.

**Konsequenz:**

- `.env.example` darf Platzhalter enthalten, aber Prod darf damit nicht starten.
- Validierungsfehler müssen klar und direkt sein.
- Dev-Ausnahmen brauchen explizite Flags.

---

## 3. Erkannte Codebase-Muster

### Gute Muster

| Muster | Bewertung | Weiter so? |
|---|---|---:|
| Application Factory | Saubere Flask-Struktur. | ✅ |
| Blueprint-Guard | Zentrale Auth-Installation. | ✅ |
| DI-Container | Testbarer als globale Service-Suche. | ✅ |
| Pydantic/Zod Contracts | Starke API-Verträge. | ✅ |
| Schema-Drift CI | Verhindert stille Contract-Brüche. | ✅ |
| DOMPurify für Markdown | Richtiger XSS-Schutzpfad. | ✅ |
| Signed Tickets | Guter Ersatz für Query-Bearer. | ✅ |
| nginx-Sidecar | Reproduzierbarer Prod-Pfad. | ✅ |
| Loopback-Defaults | Sicherer als versehentliches LAN-Publishing. | ✅ |
| Secret-Placeholder-Validation | Gute Prod-Schutzlinie. | ✅ |

### Warnmuster

| Muster | Risiko | Regel |
|---|---|---|
| Doku behauptet alten Status | Agents arbeiten gegen falsche Annahmen. | Doku-Sync als eigener PR nach jedem Hardening-Slice. |
| Soft-Gates in CI | Grün heißt nicht wirklich grün. | Soft-Gates brauchen Ablaufdatum. |
| Große Service-Dateien | Änderungen werden riskant und schwer testbar. | Neue Logik in kleine Services/Composables. |
| Single shared token | Kein Benutzerkontext, keine Rollen, schwierige Rotation. | Nur Tailnet/Single-User; für v1 ADR. |
| Keine Coverage-Schwelle | Testanzahl täuscht Sicherheit vor. | Coverage niedrig starten, schrittweise erhöhen. |
| Keine E2E-Smokes | Kernworkflow kann trotz Unit-Tests brechen. | 3 Playwright-Smokes als Minimum. |
| Temporäre CVE-Ignores | Aus temporär wird archäologisch. | Deadline + Hardstop. |

---

## 4. Technische Schulden

| ID | Bereich | Schwere | Beschreibung | Empfehlung |
|---|---|---:|---|---|
| TD-01 | Dependency Security | hoch | 6 ignorierte CVEs in CI. | Monitor + Hardstop 2026-07-30. |
| TD-02 | CI/Deployment | hoch | Prod-Proxy-Stack nicht in CI bewiesen. | `prod-stack-smoke.yml`. |
| TD-03 | AuthN/AuthZ | hoch | Shared Token statt User-/Session-Modell. | ADR + v1-Scope. |
| TD-04 | Doku | mittel | `AGENTS.md`/`CLAUDE.md` teils veraltet. | Doku-Sync-PR. |
| TD-05 | Testqualität | mittel | Evidence-Gate soft. | Hard schalten. |
| TD-06 | Coverage | mittel | Keine Coverage-Gates. | Backend/Frontend Coverage. |
| TD-07 | E2E | mittel | Kein browsernaher Kernworkflow-Test. | Playwright-Smokes. |
| TD-08 | Komplexität | mittel | Hotspot-Dateien bleiben wahrscheinlich groß. | `radon`, size-gates, Refactor-Slices. |
| TD-09 | API-Consistency | mittel | Envelope-Migration nicht vollständig belegt. | Contract-/Route-Tests. |
| TD-10 | Compliance | niedrig | Kein SBOM/License-Report. | CycloneDX/Syft. |
| TD-11 | AGPL Ops | niedrig | Kein laufzeitnaher Source-Link. | `/api/status` mit Commit/SHA/Source. |
| TD-12 | Abuse Control | niedrig-mittel | Kein Rate-Limiting. | Reverse-Proxy/App-Limits. |

---

## 5. Entwicklungsheuristiken

### Backend

1. Neue API-Felder zuerst in Pydantic modellieren.
2. API-Routen bleiben dünn.
3. Businesslogik in `services/`.
4. Externe Systeme über Ports/Adapter kapseln.
5. Keine Secrets in Logs, URLs oder Artefakten.
6. Lange Prozesse nie direkt im Request ohne Streaming/Job-State verstecken.
7. Fehlerantworten unter `/api/*` immer als JSON-Envelope.
8. Config-Probleme beim Start fail-fast melden.

### Frontend

1. Backend-Antworten strikt parsen.
2. LLM-/User-Markdown nur über Sanitizer.
3. `EventSource` nie mit Bearer-Token in URL.
4. API-Zugriff nur über zentrale API-Schicht.
5. Große Views in Komponenten und Composables schneiden.
6. UI-Strings über i18n, nicht hart in Views.
7. Fehler sichtbar machen, nicht nur `console.error`.

### Docker/Deployment

1. Default bindet an Loopback.
2. Public Access nur über Proxy/Tailnet.
3. Prod-Stack muss aus Repo-Dateien reproduzierbar sein.
4. Non-root Runtime bleibt Pflicht.
5. Capabilities droppen.
6. Read-only rootfs anstreben, aber nur wenn Runtime-Pfade sauber auf tmpfs/Volumes liegen.
7. Healthchecks müssen App und Proxy unterscheiden.

### CI/CD

1. Grün heißt: Tests, Lint, Build, Security, Contracts.
2. Soft-Gates nur mit Ablaufdatum.
3. CVE-Ignores nur mit Issue, Owner, Deadline.
4. Prod-Pfad in CI smoken.
5. Coverage messen und langsam verschärfen.
6. E2E klein halten, dafür stabil.

---

## 6. Risiken und Mitigation

| Risiko | Eintritt | Impact | Mitigation |
|---|---:|---:|---|
| Upstream-CVEs bleiben ungefixt | mittel | hoch | Monitor, Deadline, Fork-/Replacement-ADR. |
| Prod-Stack funktioniert lokal, bricht aber in CI/Server | mittel | hoch | Compose-Proxy-Smoke in CI. |
| Shared Token leakt | niedrig-mittel | hoch | Signed tickets, keine Query-Bearer, Session-ADR, Rotation-Doku. |
| LLM/Embedding-Endpoint instabil | hoch | mittel | Retry, Timeouts, klare Modellprofile, kleinere Testpfade. |
| Neo4j/Embedding-Dim mismatch | mittel | hoch | Startup-Probe + VECTOR_DIM-Validation. |
| Doku führt Agents falsch | hoch | mittel | Doku-Sync als Pflichtslice. |
| Große Dateien blockieren Refactors | mittel | mittel | Komplexitätsgate + kleine Slices. |
| Tests liefern falsche Sicherheit | mittel | hoch | Coverage + E2E + hard Evidence-Gate. |
| Public-Deployment wird falsch verstanden | mittel | hoch | README/SECURITY mit klarer Warnung, Proxy- und Auth-Doku. |
| AGPL-Verpflichtungen werden vergessen | niedrig | mittel | Source-Link + License-Report. |

---

## 7. Entscheidungsregeln für zukünftige Slices

### Sofort stoppen und ADR schreiben, wenn:

- ein neues Auth-Modell eingeführt wird,
- Multi-User-/Tenant-Funktionalität geplant wird,
- Datenmodell/Contract breaking geändert wird,
- OASIS/CAMEL ersetzt oder geforkt wird,
- Redis/File-Fallback entfernt werden soll,
- Public-Internet-Support beworben werden soll.

### Kleine PRs erzwingen, wenn:

- mehr als 5 Dateien betroffen sind,
- Contract + Frontend gleichzeitig geändert werden,
- eine Hotspot-Datei > 800 LOC angefasst wird,
- CI-Konfiguration und Code gemeinsam geändert werden,
- Doku-Status korrigiert wird.

### Nicht akzeptieren:

- neue Query-Tokens,
- neue harte Secrets in `.env.example`,
- neue rohe `/api/*` HTML-Fehler,
- neue Soft-Gates ohne Ablaufdatum,
- neue „temporäre“ CVE-Ignores ohne Issue,
- neue LLM-Marketingbegriffe im Report-Vokabular,
- direkte `current_app.extensions`-Service-Suche in neuen Services.

---

## 8. Nächste technische Entscheidungen

1. `docu/decisions/0001-auth-model.md`
   - Single-User-only v1 oder echtes Session-/Rollenmodell.

2. `docu/decisions/0002-cve-upstream-escalation.md`
   - Was passiert, wenn CAMEL/OASIS/Sentence-Transformers bis Deadline nicht patchen?

3. `docu/decisions/0003-prod-observability.md`
   - JSON-Logs, Request-IDs, Metrics, Health, Trace-Korrelation.

