# Agora — Konsolidierter Findings- & Maßnahmenplan (Audit-Snapshot 2026-05-04)

> **HISTORISCHER SNAPSHOT.** Dies ist der Audit-Drop vom 2026-05-04, der als Input für die Konsolidierung in [`PLAN.md § Status-Sync 2026-05-04`](../../PLAN.md#status-sync-2026-05-04) gedient hat. Aktueller verbindlicher Stand:
>
> - **Operative Findings & Maßnahmen:** [`PLAN.md`](../../PLAN.md)
> - **Test-Counts und Versionen:** [`docu/STATUS.md`](../STATUS.md)
> - **Subagent-Routing pro Slice:** [`docu/plan.heuristic.md`](../plan.heuristic.md)
> - **Architektur-Layer:** [`CLAUDE.md`](../../CLAUDE.md#architektur-layer-status)
>
> Diese Datei wird **nicht weiter gepflegt** — sie bleibt als Beleg dafür stehen, welche F-Findings am 2026-05-04 als erledigt vs. offen geführt wurden.

---

**Stand:** 2026-05-04  
**Repo:** `arn0ld87/agora`  
**Version:** v0.9.0 + post-tag Hardening auf `main`  
**Ziel:** Produktreife bis v1.0 ohne Doku-Drift, ungeprüfte Prod-Pfade oder Security-Ausreden. Davon hat die Welt wirklich genug.

---

## 0. Verifikationsbasis

Geprüfte Dateien:

- `README.md`
- `PLAN.md`
- `CLAUDE.md`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `SECURITY_REVIEW.md`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `docker-compose.override.yml`
- `deploy/compose/docker-compose.prod-with-proxy.yml`
- `deploy/nginx/agora.conf`
- `.github/workflows/ci.yml`
- `.github/workflows/contract-gates.yml`
- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/container.py`
- `backend/app/api/auth.py`
- `backend/app/api/simulation_stream.py`
- `backend/app/utils/auth.py`
- `frontend/package.json`
- `frontend/src/api/index.ts`
- `frontend/src/api/stream.ts`
- `frontend/src/composables/useEventStream.ts`
- `frontend/src/utils/markdown.js`
- `scripts/verify-deploy.sh`
- `docu/STATUS.md`

Nicht ausgeführt:

- keine lokale Testausführung
- kein kompletter Git-Clone
- keine dynamische Container-Ausführung
- keine DAST/SAST-Ausführung außerhalb der gelesenen CI-Konfiguration

---

## 1. Aktueller Ist-Stand

### 1.1 Bereits erledigt

| ID | Status | Bereich | Befund |
|---|---:|---|---|
| F1 | ✅ | Prod-Proxy | `deploy/compose/docker-compose.prod-with-proxy.yml` und `deploy/nginx/agora.conf` existieren. nginx deaktiviert Buffering für SSE und stellt `/healthz` bereit. |
| F2.1 | ✅ | Auth/Frontend-Token | `Dockerfile` enthält `ALLOW_BUILD_TIME_TOKEN=false` als Default. `VITE_AGORA_TOKEN` wird nicht mehr automatisch ins Bundle gebrannt. |
| F2.2 | ✅ | Query-Token | Backend lehnt `?token=` im Non-Debug-Betrieb ab. Frontend-SSE nutzt `?ticket=`. |
| F3 | ✅ | Runtime | Gunicorn läuft im Prod-Target mit `-k gevent`, nicht mehr mit sync-Worker. |
| F5a | ✅ | Status-Doku | `docu/STATUS.md` existiert als zentrale Status-/Testcount-Datei. |
| S1 | ✅ | XSS | Markdown-Rendering nutzt DOMPurify. |
| S2 | ✅ | Config | `Config.validate()` erzwingt `SECRET_KEY`, `NEO4J_PASSWORD`, `AGORA_AUTH_TOKEN` im Non-Debug-Betrieb. |
| S3 | ✅ | Docker | Compose bindet per Default an `127.0.0.1`, nutzt `no-new-privileges`, `cap_drop: ALL`, tmpfs und Pflichtpasswörter. |
| S4 | ✅ | Contracts | Pydantic/Zod-Contract-Gates und Schema-Drift-Checks existieren. |
| S5 | ✅ | Security-CI | `pip-audit`, `npm audit` und Gitleaks sind in CI vorhanden. |

### 1.2 Weiter offen

| ID | Priorität | Bereich | Befund |
|---|---:|---|---|
| R1 | 🔴 | Dependencies | 6 CVEs werden temporär ignoriert. Frist laut CI-Kommentar: 2026-07-30. |
| R2 | 🔴 | CI/Deployment | Prod-Proxy-Stack existiert, wird aber nicht als eigener CI-Smoke bewiesen. |
| R3 | 🔴 | Auth-Zielbild | Single-Token-Auth reicht für Tailnet, nicht für öffentlichen Mehrbenutzerbetrieb. |
| W1 | 🟡 | Doku-Drift | `AGENTS.md` und `CLAUDE.md` enthalten alte Statusangaben zu v0.6/gevent/SSE/Proxy. |
| W2 | 🟡 | Testqualität | `contract-gates.yml` führt Evidence-Quality noch mit `--soft` aus. |
| W3 | 🟡 | Coverage | Kein `pytest-cov`, kein Frontend-Coverage-Gate. |
| W4 | 🟡 | E2E | Keine Playwright/Cypress-Smoke-Suite für Kernworkflow. |
| W5 | 🟡 | Code-Hotspots | Große Backend-/Frontend-Dateien bleiben wahrscheinlich der nächste Refactor-Schwerpunkt. |
| W6 | 🟡 | API-Consistency | Error-/Success-Envelopes werden schrittweise eingeführt, aber nicht vollständig als abgeschlossen belegbar. |
| N1 | 🟢 | SBOM | Kein SBOM/Third-Party-License-Report. |
| N2 | 🟢 | AGPL | Kein App-/API-Hinweis auf Source-Code des laufenden Builds. |
| N3 | 🟢 | Rate Limits | Kein explizites Rate-Limiting für Ticket-, Upload- und LLM-Trigger-Endpunkte. |

---

## 2. Milestones

### M9 — Prod-Hardening finalisieren

**Ziel:** Prod-like Stack ist reproduzierbar, sicherer Default, CI-belegt.

| Task | Status | Priorität | Akzeptanz |
|---|---:|---:|---|
| M9.1 nginx-Sidecar bereitstellen | ✅ | 🔴 | `deploy/nginx/agora.conf` und Compose-Override vorhanden. |
| M9.2 Build-Time-Token entschärfen | ✅ | 🔴 | `ALLOW_BUILD_TIME_TOKEN=false` Default. |
| M9.3 `?token=` in Prod deaktivieren | ✅ | 🔴 | Backend gibt bei Non-Debug keinen Query-Token mehr frei. |
| M9.4 SSE signed tickets im Frontend | ✅ | 🔴 | `frontend/src/api/stream.ts` holt Ticket über `/api/auth/ticket`. |
| M9.5 Gunicorn gevent | ✅ | 🔴 | Dockerfile nutzt `-k gevent`. |
| M9.6 Prod-Stack-Smoke in CI | ⬜ | 🔴 | Neuer Workflow startet Compose mit Prod+Proxy und prüft `/healthz`, `/health`, `/`, Ticket-Ausstellung und optional SSE-Connect. |
| M9.7 Doku-Sync M9 | ⬜ | 🟡 | `README.md`, `CLAUDE.md`, `AGENTS.md`, `STATUS.md`, `SECURITY_REVIEW.md` widersprechen sich nicht mehr. |

### M10 — Security und Dependency-Risiken schließen

**Ziel:** Temporäre Security-Ausnahmen sind überwacht und laufen nicht still weiter.

| Task | Status | Priorität | Akzeptanz |
|---|---:|---:|---|
| M10.1 CVE-Monitor-Workflow | ⬜ | 🔴 | `.github/workflows/cve-monitor.yml` läuft wöchentlich ohne `--ignore-vuln` und reportet Abweichungen. |
| M10.2 CVE-Hardstop | ⬜ | 🔴 | Ab 2026-07-30 darf CI nicht mehr mit den sechs ignorierten Advisories grün werden. |
| M10.3 Dependency Risk Register aktualisieren | ⬜ | 🟡 | `docu/dependency-risk-register.md` enthält Owner, Upstream-Link, Deadline, Eskalationspfad. |
| M10.4 Auth-ADR | ⬜ | 🔴 | ADR entscheidet zwischen HttpOnly-Session, Bearer+Refresh oder bewusstem Single-User-only-v1-Verzicht. |
| M10.5 Rate-Limit-Konzept | ⬜ | 🟡 | Upload, Ticket, LLM-Trigger und Report-Endpunkte haben Limits auf App- oder Reverse-Proxy-Ebene. |

### M11 — Test- und Qualitätsgates härten

**Ziel:** Tests sind nicht nur zahlreich, sondern aussagekräftig. Verrücktes Konzept, ich weiß.

| Task | Status | Priorität | Akzeptanz |
|---|---:|---:|---|
| M11.1 Evidence-Gate hard schalten | ⬜ | 🟡 | `--soft` aus `contract-gates.yml` entfernt oder per dokumentiertem Übergangsflag steuerbar. |
| M11.2 Backend-Coverage | ⬜ | 🟡 | `pytest-cov`, initial `--cov-fail-under=70`, Report in CI. |
| M11.3 Frontend-Coverage | ⬜ | 🟡 | `@vitest/coverage-v8`, initial 60 %, CI-Ausgabe. |
| M11.4 Playwright-Smokes | ⬜ | 🟡 | 3 Tests: Health/Login, Upload+Graph-Build, Persona/Simulation/Report-Minimalpfad. |
| M11.5 Complexity-Gate | ⬜ | 🟡 | `radon` für Backend, ESLint/size-limit für Frontend, Allowlist für Altlasten. |
| M11.6 API-Envelope-Gate | ⬜ | 🟡 | Tests verhindern rohe HTML-/dict-/uneinheitliche Fehlerantworten unter `/api/*`. |

### M12 — Feature-Backlog bis v1.0

**Ziel:** Offene Layer-7/8-Funktionen fertigstellen oder bewusst aus v1.0 schneiden.

| Task | Status | Priorität | Akzeptanz |
|---|---:|---:|---|
| M12.1 Graph-Diff API finalisieren | ⬜ | 🟡 | API-Contract, Tests, Frontend-kompatible DTOs. |
| M12.2 Compare-API | ⬜ | 🟡 | Vergleich zweier Runs/Branches mit stabiler Contract-Struktur. |
| M12.3 Compare-UI | ⬜ | 🟡 | UI kann zwei Runs auswählen und Unterschiede anzeigen. |
| M12.4 RunsDashboard finalisieren | ⬜ | 🟡 | `/runs` ist stabil, filterbar, fehlerresistent. |
| M12.5 Persona-Diff | ⬜ | 🟡 | Persona-Änderungen sind nachvollziehbar. |
| M12.6 Approve/Reject/Regenerate-UX | ⬜ | 🟡 | Review-Workflow ist ohne JSON-Gefrickel bedienbar. |

### M13 — Release-Hygiene und Compliance

**Ziel:** v1.0 ist nachvollziehbar, lizenzkonform und betreibbar.

| Task | Status | Priorität | Akzeptanz |
|---|---:|---:|---|
| M13.1 Release-Marker | ⬜ | 🟡 | `0.9.x-dev`, `0.10.0-alpha` oder klarer v1.0-Pre-Release-Tag. |
| M13.2 SBOM | ⬜ | 🟢 | CycloneDX/Syft-Artifact in CI. |
| M13.3 License-Report | ⬜ | 🟢 | Third-party license report für npm und Python. |
| M13.4 AGPL-Source-Link | ⬜ | 🟢 | App/Health zeigt Commit-SHA und Source-URL. |
| M13.5 Doku-Archivierung | ⬜ | 🟢 | Alte Pläne nach `docu/history/`, aktive Quellen klar: `PLAN.md`, `docu/STATUS.md`, `docu/ROADMAP.md`, ADRs. |

---

## 3. Priorisierte To-do-Liste

### 🔴 Kritisch

1. **Prod-Stack-Smoke in CI**
   - Datei: `.github/workflows/prod-stack-smoke.yml`
   - Prüfen: `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build`
   - Checks: `/healthz`, `/health`, `/`, `/api/auth/ticket`, optional SSE-Open.

2. **CVE-Monitor + Hardstop**
   - Datei: `.github/workflows/cve-monitor.yml`
   - Wöchentlich ohne Ignore laufen lassen.
   - Ab 2026-07-30 keine ignorierten CVEs mehr zulassen.

3. **Auth-Zielbild entscheiden**
   - Datei: `docu/decisions/0001-auth-model.md`
   - Entscheidung: Single-User-only, HttpOnly-Session oder Bearer+Refresh.
   - Ergebnis muss v1.0-Scope festlegen.

### 🟡 Wichtig

4. **Doku-Drift bereinigen**
   - Dateien: `AGENTS.md`, `CLAUDE.md`, `STATUS.md`, `SECURITY_REVIEW.md`
   - Gevent, Proxy, signed tickets und Layer-9-Status auf echten Code-Stand bringen.

5. **Evidence-Gate hard schalten**
   - Datei: `.github/workflows/contract-gates.yml`
   - `--soft` entfernen.
   - Falls noch nicht möglich: Grund und Exit-Kriterien dokumentieren.

6. **Coverage-Gates einführen**
   - Backend: `pytest-cov`, Startwert 70 %.
   - Frontend: `@vitest/coverage-v8`, Startwert 60 %.

7. **E2E-Minimalpfad**
   - Tool: Playwright.
   - Tests: Health/Login, Upload+Graph, Minimalreport.

8. **Komplexität messen**
   - Backend: `radon`.
   - Frontend: große Vue-Dateien und JS-Reste identifizieren.
   - Keine neuen Hotspots ohne Allowlist.

### 🟢 Nice-to-have

9. **SBOM/License-Report**
   - CycloneDX oder Syft.
   - CI-Artefakt.

10. **AGPL-Operationalisierung**
    - Build-Commit und Source-URL in `/health` oder `/api/status`.

11. **Rate-Limits**
    - `/api/auth/ticket`, Uploads, LLM-Trigger, Report-Generation.

---

## 4. Arbeitsreihenfolge

1. **PR 1:** Doku-Sync für `AGENTS.md`, `CLAUDE.md`, `STATUS.md`, `SECURITY_REVIEW.md`.
2. **PR 2:** `prod-stack-smoke.yml`.
3. **PR 3:** `cve-monitor.yml` + Dependency Risk Register.
4. **PR 4:** Evidence-Gate hard + Coverage-Grundlage.
5. **PR 5:** Auth-ADR + Rate-Limit-Konzept.
6. **PR 6:** Playwright-Smokes.
7. **PR 7:** Komplexitätsgate + Hotspot-Backlog.

---

## 5. Definition of Done für v1.0

v1.0 ist erst vertretbar, wenn:

- keine ignorierten CVEs ohne aktive Ausnahmefrist in CI sind,
- Prod-Proxy-Stack in CI grün läuft,
- Auth-Zielbild dokumentiert und umgesetzt oder bewusst auf Single-User begrenzt ist,
- Evidence-Gate hart ist,
- Coverage-Gates existieren,
- mindestens drei E2E-Smokes grün sind,
- Doku-Status nicht mehr widersprüchlich ist,
- ein Release-Tag mit Changelog existiert,
- SBOM/License-Report zumindest generierbar sind.

