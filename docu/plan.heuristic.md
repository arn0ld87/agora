# plan.heuristic.md — Agora Architektur-Heuristiken, ADRs und Subagent-Mapping

**Stand:** 2026-05-04  
**Repo:** [`arn0ld87/agora`](https://github.com/arn0ld87/agora) · v0.9.0+ post-tag  
**Status:** offizielle Heuristik-Datei. Konsolidiert aus: Backup-Master-Mapping (Stand 2026-05-03), Audit-ADR-Snapshot vom 2026-05-04 ([`docu/history/2026-05-04-plan-heuristic-adr-snapshot.md`](history/2026-05-04-plan-heuristic-adr-snapshot.md)), Code-Verifikation vom 2026-05-04.

## Zweck

Diese Datei ist die **kompakte technische Gedächtnisstütze für zukünftige Slices** und beantwortet:

- Welche Architekturentscheidungen gelten (ADRs)?
- Welche Subagent-Profile sind für welche Slice-Klasse zuständig?
- Welche Code-Muster sind erwünscht, welche sind Warnsignale?
- Welche technischen Schulden sind aktiv?
- Welche Risiken brauchen Mitigation?
- Welche Slash-Command-Vorlagen existieren bzw. fehlen?

Operative Findings: [`PLAN.md`](../PLAN.md). Test-Counts und Layer-Status: [`docu/STATUS.md`](STATUS.md).

---

## 1. Architektur-Entscheidungen (ADRs in Kurzform)

Volltext-ADRs gehören nach `docu/decisions/`. Hier die geltenden Kernentscheidungen.

### ADR-0001 — Local-first bleibt Kernprinzip

**Entscheidung:** Agora bleibt primär ein lokaler/Tailnet-Single-User-Simulator.

**Begründung:** LLM-/Embedding-/Graph-Workloads sind teuer, langsam und schwer multi-tenant-sicher. Lokale Ollama-/Neo4j-Setups passen zum ursprünglichen Use Case. Security-Baseline ist für private Netze deutlich realistischer als für Public SaaS.

**Konsequenz:** Public-Internet-Betrieb ist nicht Standard. README/SECURITY/Docker-Doku müssen klar sagen: kein öffentliches Mehrbenutzer-SaaS ohne zusätzliche AuthN/AuthZ, Rate-Limits und Abuse-Schutz.

### ADR-0002 — Stack: Flask + Pydantic v2 + Vue 3 + Neo4j + Ollama-kompatibel

**Entscheidung:** Stack bleibt Flask/Python 3.11, Vue 3/Vite/Pinia, Neo4j 5.18+, OpenAI-kompatible LLM-Endpunkte.

**Konsequenz:** Keine Provider-Lock-ins. Provider-spezifische Sonderlogik bleibt in `utils/llm_client.py` isoliert. Embedding-Dimensionen werden fail-fast validiert.

### ADR-0003 — Pydantic ist Backend-Contract-Quelle, Zod ist Frontend-Spiegel

**Entscheidung:** API-Verträge werden in Pydantic v2 modelliert (`extra="forbid"`) und per JSON-Schema gespiegelt.

**Heuristik:**

- Neue API-Struktur = zuerst Pydantic-Modell.
- Keine Inline-JSON-Schemas.
- Frontend-Zod immer aus Backend-Contract ableiten oder bewusst spiegeln.
- Schema-Drift-Check `git diff --exit-code schemas/` ist CI-Pflicht.

### ADR-0004 — URL-bound Auth nur über kurzlebige signed tickets

**Entscheidung:** EventSource/Download-URLs nutzen **niemals** long-lived Bearer-Tokens.

**Begründung:** `EventSource` kann keine Custom Header. `?token=` landet in Proxy-Logs, Browser-History und Referern. Signed tickets sind kurzlebig und scope-bound.

**Konsequenz:**

- SSE nutzt `POST /api/auth/ticket` + `?ticket=`.
- Backend blockt `?token=` im Non-Debug-Betrieb (verifiziert in `backend/app/utils/auth.py::_extract_token`).
- Neue URL-basierte Endpunkte müssen `allow_ticket_auth()` verwenden.

### ADR-0005 — Prod läuft über Gunicorn gevent + nginx-Sidecar

**Entscheidung:** Prod-Target nutzt Gunicorn mit gevent; öffentlich erreichbare Topologie läuft über Reverse-Proxy.

**Konsequenz:**

- CI muss den kompletten Prod-Stack smoken (M9.6 vorhanden fuer `main`/Tags/`workflow_dispatch`; PR-Trigger seit 2026-05-06 pausiert und vor Release neu zu bewerten).
- nginx-Konfiguration ist Teil des Produkts (`deploy/nginx/agora.conf`), nicht Betreiber-Folklore.
- Proxy-Timeouts und `proxy_buffering off` sind Pflicht für SSE.

### ADR-0006 — Redis Eventbus bevorzugt, File-Fallback bleibt

**Entscheidung:** Redis ist Compose-Default; File-Polling bleibt Offline-Fallback.

**Konsequenz:**

- Eventbus-Zugriff nur über Abstraktion (`SimulationEventBus`).
- Kein direkter Redis-Code in API-Routen.
- Fallback-Verhalten muss getestet bleiben.

### ADR-0007 — Config fail-fast statt kaputter Runtime

**Entscheidung:** Fehlende Secrets, falsche Embedding-Dimensionen und fehlende Auth im Non-Debug-Betrieb stoppen den Start.

**Konsequenz:**

- `.env.example` darf Platzhalter enthalten, aber Prod darf damit nicht starten.
- `Config.validate()` erkennt Placeholder-Werte.
- Dev-Ausnahmen brauchen explizite Flags (`AGORA_ALLOW_ANONYMOUS=true`).

### Geplant (offen)

- **ADR-0008 / 0001-auth-model.md** (M10.4): Single-User-only-v1, HttpOnly-Session oder Bearer+Refresh — entscheidet v1.0-Scope.
- **ADR-0009 / 0002-cve-upstream-escalation.md** (M10.2): Was passiert, wenn CAMEL/OASIS/Sentence-Transformers bis 2026-07-30 nicht patchen (Vendoring vs. Soft-Fork vs. Replacement)?
- **ADR-0010 / 0003-prod-observability.md**: JSON-Logs, Request-IDs, Metrics, Health, Trace-Korrelation.

---

## 2. Master-Mapping: Slice → Subagent → Akzeptanz

Jede Zeile = ein Branch, ein Commit, ein Verify-Gate, ein FF-Push. Reihenfolge folgt der Roadmap aus [`PLAN.md`](../PLAN.md). Status-Spalte wird nach Verify aktualisiert (✅ = code-verifiziert grün, ⬜ = offen).

| Slice | Status | Finding | Subagent | Slash | Modell | Akzeptanz (kopierbarer Check) |
|---|---|---|---|---|---|---|
| **M9.1** | ✅ | F1 Reverse-Proxy | `agora-refactor-worker` | `/agora-next-task` | Sonnet | `ls deploy/nginx/agora.conf deploy/compose/docker-compose.prod-with-proxy.yml` exists |
| **M9.2** | ✅ | F2.1 Bundle-Token-Gate | `agora-refactor-worker` + `agora-frontend-worker` | `/agora-next-task` | Sonnet | `grep "ALLOW_BUILD_TIME_TOKEN=false" Dockerfile` matches |
| **M9.3** | ✅ | F2.2 `?token=` aus Prod | `agora-refactor-worker` | `/agora-next-task` | Sonnet | `cd backend && uv run pytest tests/test_auth.py -k query -v` grün |
| **M9.4** | ✅ | SSE-Auth-Frontend (signed tickets) | `agora-frontend-worker` | `/agora-next-task` | Sonnet | `grep "?ticket=" frontend/src/api/stream.ts` matches |
| **M9.5** | ✅ | F3 Gunicorn-Gevent | `agora-refactor-worker` + `agora-test-worker` | `/agora-next-task` | Sonnet | `grep -A3 '^CMD' Dockerfile \| grep "gevent"` matches |
| **M9.6** | 🟡 | Prod-Stack-Smoke in CI | `agora-test-worker` | `/agora-next-task` | Sonnet | `docker-image.yml::prod-proxy-smoke` läuft auf `push: [main, tags]` und `workflow_dispatch`. PR-Trigger ist seit 2026-05-06 wegen ~30 min Laufzeit pausiert und vor dem finalen Release-Gate neu zu bewerten. `verify-deploy.sh` smoket `/healthz`, `/health`, `/`, `/api/auth/ticket`. |
| **M9.7** | ✅ | Doku-Sync 2026-05-04 | `agora-doc-worker` | `/agora-next-task` | Haiku | PR #271 gemerged. `grep "v0.6.0" AGENTS.md` leer. |
| **M10.1** | ✅ | F4.1 CVE-Monitor cron | `agora-doc-worker` | `/agora-next-task` | Haiku | `.github/workflows/cve-monitor.yml` läuft Mo 06:00 UTC `pip-audit --strict` ohne `--ignore-vuln`, schreibt in `$GITHUB_STEP_SUMMARY`, lädt Output als Artefakt. |
| **M10.2** | ✅ | F4.2 CVE-Hardstop 2026-07-30 | `agora-doc-worker` | `/agora-next-task` | Haiku | `cve-monitor.yml::Hardstop-Gate` failt ab 2026-07-30, wenn Audit non-zero. `ci.yml` Kommentar verweist auf den Hardstop. |
| **M10.3** | ✅ | Dependency Risk Register erweitern | `agora-doc-worker` | `/agora-next-task` | Haiku | Eskalationspfad-Sektion + neue Upstream-Release-Watch-Spalte in `docu/dependency-risk-register.md` (Owner-Spalte war bereits vorhanden). |
| **M10.4** | ✅ | Auth-Zielbild-ADR | `agora-doc-worker` (+ Lead) | `/agora-next-task` | Haiku + Senior | `docu/decisions/0001-auth-model.md` **Accepted 2026-05-04** (Option A: Single-User-only-v1). `/api/status` liefert jetzt `auth_mode: "single_user_token"` (Code-Update in `_get_auth_mode()`). Folge: README/security-hardening-Update bleibt offen. |
| **M10.5** | ✅ | Rate-Limit-Konzept | `agora-refactor-worker` | `/agora-next-task` | Sonnet | Limits für `/api/auth/ticket`, Uploads, LLM-Trigger, Report-Gen vorhanden (PR #303–#306, Issue #302) |
| **M11.1** | ✅ | Evidence-Gate hard schalten | `agora-test-worker` | `/agora-next-task` | Sonnet | `--soft` aus `.github/workflows/contract-gates.yml` entfernt. Hard-Gate misst über `tests/eval/fixtures/good/` (Schwellen 0.85/0.75/0.10), Bad-Cases nach `tests/eval/fixtures/bad/` verschoben (gepinnt durch Snapshot-Test). 13/13 Eval-Tests grün. |
| **M11.2** | ⬜ | Backend-Coverage 70 % | `agora-test-worker` | `/agora-next-task` | Sonnet | `cd backend && uv run pytest --cov=app --cov-fail-under=70` grün |
| **M11.3** | ⬜ | Frontend-Coverage 60 % | `agora-test-worker` | `/agora-next-task` | Sonnet | `cd frontend && npm run test:coverage` ≥ 60 % |
| **M11.4** | ⬜ | Playwright-Smokes (3 Tests) | `agora-test-worker` | `/agora-next-task` | Sonnet | `npx playwright test` 3 Tests grün auf nightly |
| **M11.5** | ⬜ | Komplexitäts-Gate (`radon`/size-limit) | `agora-test-worker` | `/agora-next-task` | Sonnet | `cd backend && uv run radon cc -nc app` grün |
| **M11.6** | ⬜ | API-Envelope-Gate | `agora-test-worker` | `/agora-next-task` | Sonnet | Tests verhindern rohe HTML-/dict-Fehler unter `/api/*` |
| **M12.1** | ⬜ | F7.1 `report_agent.py` < 1200 LOC (#202) | `agora-refactor-worker` | `/agora-next-task` | Sonnet | `wc -l backend/app/services/report_agent.py` < 1200; Eval-Snapshots stabil |
| **M12.2** | ⬜ | F7.2 `simulation_runner.py` schneiden | `agora-refactor-worker` | `/agora-next-task` | Sonnet | `wc -l backend/app/services/simulation_runner.py` < 1000 |
| **M12.3** | ⬜ | F8.1 `Step2EnvSetup.vue` aufteilen (#203) | `agora-frontend-worker` | `/agora-next-task` | Sonnet | `wc -l frontend/src/components/Step2EnvSetup.vue` < 800 |
| **M12.4** | ⬜ | F8.2 `Step4Report.vue` aufteilen | `agora-frontend-worker` | `/agora-next-task` | Sonnet | `wc -l frontend/src/components/Step4Report.vue` < 800 |
| **M12.5** | ⬜ | F11 TS-Migration Restdateien (#73) | `agora-frontend-worker` | `/agora-next-task` | Sonnet | `find frontend/src -name '*.js' -not -path '*/node_modules/*' \| wc -l` ≤ 3 |
| **M12.6** | ⬜ | F9 #74 Graph-Diff Modell + API | `agora-refactor-worker` | `/agora-next-task` | Sonnet | API-Contract + Tests + Frontend-DTOs |
| **M12.7** | ⬜ | F9 #66 Compare-API für Kernmetriken | `agora-refactor-worker` | `/agora-next-task` | Sonnet | Vergleich zweier Runs/Branches mit stabiler Contract-Struktur |
| **M12.8** | ⬜ | F9 #76 Diff-/Confidence-UI | `agora-frontend-worker` | `/agora-next-task` | Sonnet | UI nach #74+#66 nutzbar |
| **M12.9** | ⬜ | F9 #67 Compare-UI für zwei Branches | `agora-frontend-worker` | `/agora-next-task` | Sonnet | UI kann zwei Runs auswählen |
| **M12.10** | ⬜ | F9 #63 RunsDashboard.vue | `agora-frontend-worker` | `/agora-next-task` | Sonnet | `/runs` stabil, filterbar, fehlerresistent |
| **M12.11** | ⬜ | F10 #69 Persona-Diff | `agora-frontend-worker` + `agora-refactor-worker` | `/agora-next-task` | Sonnet | Persona-Änderungen nachvollziehbar |
| **M12.12** | ⬜ | F10 #70 Approve/Reject/Regenerate-UX | `agora-frontend-worker` | `/agora-next-task` | Sonnet | Review-Workflow ohne JSON-Gefrickel |
| **M12.13** | ⬜ | F10 #137 Graph-Build Batch-Marker + Auto-Freeze | `agora-refactor-worker` + `agora-frontend-worker` | `/agora-next-task` | Sonnet | Batch-Marker im UI sichtbar |
| **M13.1** | ⬜ | F14.1 `/api/version` mit SHA + UI-Footer | `agora-frontend-worker` + `agora-refactor-worker` | `/agora-next-task` | Sonnet | `curl /api/version \| jq .commit_sha` matches |
| **M13.2** | ⬜ | F14.2 SBOM (CycloneDX/Syft) | `agora-doc-worker` | `/agora-next-task` | Haiku | CI-Artifact `sbom.cdx.json` exists |
| **M13.3** | ⬜ | Third-Party License-Report | `agora-doc-worker` | `/agora-next-task` | Haiku | `docu/THIRD-PARTY-LICENSES.md` CI-gepflegt |
| **M13.4** | ⬜ | F13 Doku-Konsolidierung (`docu/history/`) | `agora-doc-worker` | `/agora-next-task` | Haiku | `find docu/ -maxdepth 1 -type f \| wc -l` ≤ 25 |
| **M13.5** | ⬜ | Release v1.0.0 | `agora-doc-worker` | `/agora-next-task` | Haiku | `git tag` enthält `v1.0.0` |

---

## 3. Subagent-Auslastung pro Phase

| Subagent | Aktive Slices (offen) | Token-Schätzung |
|---|---|---|
| `agora-test-worker` | M9.6, M11.1–M11.6 | hoch |
| `agora-refactor-worker` | M12.1, M12.2, M12.6, M12.7, M12.13 | hoch |
| `agora-frontend-worker` | M12.3, M12.4, M12.5, M12.8, M12.9, M12.10, M12.11, M12.12, M13.1 | hoch |
| `agora-doc-worker` | M9.7, M10.1, M10.2, M10.3, M10.4, M13.2, M13.3, M13.4, M13.5 | mittel |
| `agora-evidence-auditor` | nur Audit-Reads bei M11.1 (Evidence-Gate hard) und M12.1 (Snapshot-Stabilität) | niedrig |

Wenn `agora-refactor-worker` zur Engstelle wird, lassen sich M12-Refactors und M11.5 (Komplexitäts-Gate) in **parallelen Worktrees** vorbereiten — Reviews/Verify bleiben sequenziell beim Lead.

---

## 4. Reihenfolge-Heuristik (für Lead bei `/agora-next-task`)

### Sequenziell (harte Reihenfolge)

```
M9.6 (Prod-Smoke)  →  M9.7 (Doku-Sync, dieser Slice)
                  →  M10.1 (CVE-Monitor)  →  M10.2 (Hardstop)  →  M10.3 (Risk-Register)
                  →  M10.4 (Auth-ADR)     →  M10.5 (Rate-Limits)
                  →  M11.1..M11.6 (Test-Schärfe)
                  →  M12.1..M12.13 (Hotspots + Feature-Welle)
                  →  M13.1..M13.5 (v1.0-Vorbereitung)
```

**Begründungen:**

- **M9.6 vor allem anderen** in M9: ohne grünen Smoke ist M9 blind — die F1/F2/F3-Slices liefern lokal, aber der CI-Beweis fehlt.
- **M10.4 (Auth-ADR) vor M10.5 (Rate-Limits)**: ohne Auth-Zielbild lässt sich der Rate-Limit-Scope nicht sauber schneiden.
- **M11.1 (Evidence-Gate hard) vor M11.2/M11.3 (Coverage)**: weicher Gate macht Coverage-Drift möglich.
- **M12.1 (`report_agent.py`-Schnitt) vor M12.2/M12.6**: andere Refactors lehnen sich an die Façade-Pattern aus #202 an.

### Parallel zulässig (verschiedene Worktrees, keine Datei-Konflikte)

- **M10.1 (CVE-Monitor) ‖ M10.3 (Risk-Register)** — beide Doku, disjunkt.
- **M11.2 (Backend-Coverage) ‖ M11.3 (Frontend-Coverage)** — getrennte Stacks.
- **M12.3 (`Step2EnvSetup.vue`) ‖ M12.4 (`Step4Report.vue`)** — disjunkte Vue-Files, derselbe Subagent kann sie sequenziell schnell abarbeiten.

### Nicht parallel

- **M11.1 ⇄ M11.2/M11.3** — Evidence-Gate-Switch ändert die Test-Run-Erwartung; erst Gate, dann Coverage.
- **M12.1 ⇄ M12.6** — beide berühren die Report-Agent-Façade.

---

## 5. Code-Muster

### Gute Muster (weiter so)

| Muster | Bewertung |
|---|---|
| Application Factory | Saubere Flask-Struktur. |
| Blueprint-Guard (`install_blueprint_guard`) | Zentrale Auth-Installation. |
| DI-Container (`AgoraContainer`) | Testbarer als globale Service-Suche. |
| Pydantic v2 + Zod-Spiegel + JSON-Schema-Dump | Starke API-Verträge. |
| Schema-Drift CI | Verhindert stille Contract-Brüche. |
| DOMPurify für Markdown | Richtiger XSS-Schutzpfad. |
| Signed Tickets | Guter Ersatz für Query-Bearer. |
| nginx-Sidecar | Reproduzierbarer Prod-Pfad. |
| Loopback-Defaults + `AGORA_BIND_HOST`-Override | Sicherer als versehentliches LAN-Publishing. |
| Secret-Placeholder-Validation (`Config.validate()`) | Gute Prod-Schutzlinie. |
| `OASIS_DB_PATH` pro Sim | Verhindert Cross-Run-Kontamination. |
| `apply_camel_context_floor()` zentral | Verhindert Memory-Cap-Drift. |

### Warnmuster (vermeiden)

| Muster | Risiko | Regel |
|---|---|---|
| Doku behauptet alten Status | Agents arbeiten gegen falsche Annahmen. | Doku-Sync als eigener PR nach jedem Hardening-Slice. |
| Soft-Gates in CI ohne Ablaufdatum | Grün heißt nicht wirklich grün. | Soft-Gates brauchen Ablaufdatum. |
| Große Service-Dateien | Änderungen werden riskant und schwer testbar. | Neue Logik in kleine Services/Composables. |
| Single shared token als Auth | Kein Benutzerkontext, keine Rollen, schwierige Rotation. | Nur Tailnet/Single-User; für v1 ADR. |
| Keine Coverage-Schwelle | Testanzahl täuscht Sicherheit vor. | Coverage niedrig starten, schrittweise erhöhen. |
| Keine E2E-Smokes | Kernworkflow kann trotz Unit-Tests brechen. | 3 Playwright-Smokes als Minimum. |
| Temporäre CVE-Ignores | Aus temporär wird archäologisch. | Deadline + Hardstop. |
| Hartkodierte `token_limit` in CAMEL/OASIS | Kappt Memory bei 8192 unabhängig vom Modell. | Immer `_resolve_memory_token_limit(model_name)`. |
| `CREATE VECTOR INDEX … IF NOT EXISTS` ohne Dim-Check | Stiller Drift bei Embedding-Wechsel. | Issue #263: `_ensure_schema()` muss bei Mismatch droppen + recreaten. |

---

## 6. Technische Schulden (Live-Register)

| ID | Bereich | Schwere | Beschreibung | Tracker |
|---|---|---:|---|---|
| TD-01 | Dependency Security | hoch | 6 ignorierte CVEs in CI bis 2026-07-30. | #121–#126 / M10.1+M10.2 |
| TD-02 | CI/Deployment | mittel | Prod-Proxy-Stack wird auf `main`/Tags/`workflow_dispatch` gesmoked; PR-Trigger ist fuer schnelle Iteration pausiert. | M9.6 / Final-Release-Gate |
| TD-03 | AuthN/AuthZ | hoch | Shared Token statt User-/Session-Modell. | M10.4 |
| TD-04 | Test-Qualität | mittel | Evidence-Gate weiterhin `--soft`. | M11.1 |
| TD-05 | Coverage | mittel | Keine Coverage-Gates. | M11.2 + M11.3 |
| TD-06 | E2E | mittel | Kein browsernaher Kernworkflow-Test. | M11.4 |
| TD-07 | Komplexität | mittel | `report_agent.py` 2400 LOC, `simulation_runner.py` 1904, `Step2EnvSetup.vue` 1804, `Step4Report.vue` 1287. | #202, #203, M12.1–M12.4 |
| TD-08 | API-Consistency | mittel | Envelope-Migration nicht vollständig belegt. | M11.6 |
| TD-09 | Vector-Index | mittel | Drift bei Embedding-Modell-Wechsel. | #263 |
| TD-10 | Compliance | niedrig | Kein SBOM/License-Report. | M13.2 + M13.3 |
| TD-11 | AGPL Ops | niedrig | Kein laufzeitnaher Source-Link. | M13.1 |
| TD-12 | Abuse Control | erledigt | App-seitige Fixed-Window-Rate-Limits vorhanden; Distributed-Limiter nur bei erweitertem Deployment-Modell erneut bewerten. | M10.5 |
| TD-13 | Doku-Fragmentierung | niedrig | 130+ Files in `docu/` ohne klare Vorderbühne. | M13.4 |

---

## 7. Risiken und Mitigation

| Risiko | Eintritt | Impact | Mitigation |
|---|---:|---:|---|
| Upstream-CVEs bleiben ungefixt | mittel | hoch | Monitor (M10.1), Hardstop 2026-07-30 (M10.2), Fork-/Replacement-ADR. |
| Prod-Stack lokal grün, in CI rot | mittel | hoch | Compose-Proxy-Smoke in CI (M9.6) auf `main`/Tags/manuell; PR-Reaktivierung vor Release. |
| Shared Token leakt | niedrig-mittel | hoch | Signed tickets ✅, `?token=`-Block in Prod ✅, Auth-ADR (M10.4), Rotation-Doku. |
| LLM-/Embedding-Endpoint instabil | hoch | mittel | Retry, Timeouts, klare Modellprofile, kleinere Testpfade. |
| Neo4j/Embedding-Dim mismatch | mittel | hoch | Startup-Probe + `VECTOR_DIM`-Validation; Hardening in #263. |
| Doku führt Agents falsch | hoch | mittel | Doku-Sync als Pflichtslice nach jedem Hardening-Slice. |
| Große Dateien blockieren Refactors | mittel | mittel | Komplexitätsgate (M11.5) + kleine Slices. |
| Tests liefern falsche Sicherheit | mittel | hoch | Coverage (M11.2/3) + E2E (M11.4) + hard Evidence-Gate (M11.1). |
| Public-Deployment wird falsch verstanden | mittel | hoch | README/SECURITY mit klarer Warnung, Proxy- und Auth-Doku. |
| AGPL-Verpflichtungen werden vergessen | niedrig | mittel | Source-Link (M13.1) + License-Report (M13.3). |
| `gevent.monkey.patch_all()` ↔ OASIS-Subprozess bricht | mittel | hoch | `scripts/verify-deploy.sh`-Smoke vor jedem Slice-Touch im Prod-Pfad. |

---

## 8. Entscheidungsregeln für zukünftige Slices

### Sofort stoppen und ADR schreiben, wenn:

- ein neues Auth-Modell eingeführt wird → ADR-0008 (M10.4) zwingend zuerst.
- Multi-User-/Tenant-Funktionalität geplant wird.
- Datenmodell/Contract breaking geändert wird.
- OASIS/CAMEL ersetzt oder geforkt wird → ADR-0009 zwingend.
- Redis/File-Fallback entfernt werden soll.
- Public-Internet-Support beworben werden soll.

### Kleine PRs erzwingen, wenn:

- mehr als 5 Dateien betroffen sind.
- Contract + Frontend gleichzeitig geändert werden.
- eine Hotspot-Datei > 800 LOC angefasst wird.
- CI-Konfiguration und Code gemeinsam geändert werden.
- Doku-Status korrigiert wird (eigener Doku-Sync-PR).

### Nicht akzeptieren:

- Neue Query-Tokens (`?token=`).
- Neue harte Secrets in `.env.example`.
- Neue rohe `/api/*` HTML-Fehler.
- Neue Soft-Gates ohne Ablaufdatum.
- Neue „temporäre" CVE-Ignores ohne Issue, Owner, Deadline und Hardstop.
- Neue LLM-Marketingbegriffe im Report-Vokabular (Wording-Glossar v1, Issue #175).
- Direkte `current_app.extensions`-Service-Suche in neuen Services (immer `AgoraContainer`).
- Hartkodierte `token_limit`-Defaults in CAMEL-/OASIS-Anbindungen.

---

## 9. Hardstops (gelten weiterhin, ergänzt 2026-05-04)

- Kein Sammel-PR über mehrere Layer.
- Kein `Closes #N`, wenn der Issue nur vorbereitet wurde.
- Kein Dependency-Upgrade gegen harte Third-Party-Pins ohne Testlauf (gilt explizit für CVE-Pins).
- Kein Frontend-TypeScript-Big-Bang vor stabilen API-Schemas (Layer 0 ist stabil → M12.5 ist sicher).
- Kein Prod-Deployment-Slice zusammen mit Report-Refactor.
- Kein Auto-Fix-Loop nach rotem Verify. Fehler reporten, Worktree stehen lassen.
- Kein Big-Bang-Refactor an `report_agent.py` ohne Snapshot-Eval-Tests grün vor + nach (M12.1, abgesichert durch Sub-Slice 17 Eval-Suite).
- Kein gevent-Switch ohne Fork-Safety-Tests für Neo4j+Redis-Pools (rückblickend zu M9.5 dokumentiert).
- Kein Ruff-Regel-Bump als Sammel-Diff — gescopter Rollout wie beim ersten Default-Strict-Move (M11.5).
- **Kein `git push --no-verify`** ohne explizite User-Freigabe.
- **Kein Merge auf `main`** ohne Gemini-Findings-Sichtung (siehe `CLAUDE.md` PR-Workflow).

---

## 10. Slash-Command-Vorlagen

### Aktiv

`.claude/commands/`:

- `/agora-next-task` — Master-Orchestrator: pickt nächsten offenen Sub-Slice aus PLAN.md, dispatched passenden Subagent, verifiziert, committet, pusht.
- `/verify-after-subagent` — Pflicht-Verifikation nach jedem Subagent-Run (sequential gate).
- `/fix-task-01..04-*` — Templates aus dem Layer-0–4-Refactor (inhaltlich abgearbeitet; können archiviert werden).

### Geplant (noch nicht angelegt)

- `/fix-task-05-prod-stack-smoke` — M9.6: Prod-Stack-Smoke-Workflow erzeugen bzw. PR-Trigger vor Release reaktivieren.
- `/fix-task-06-cve-monitor` — M10.1/M10.2: CVE-Monitor + Hardstop.
- `/fix-task-07-evidence-hard` — M11.1: `--soft` aus Evidence-Gate entfernen.

Wenn ein neuer Slash-Command angelegt wird, dieselbe Struktur nutzen wie `/fix-task-01..04`: Vorab-Verifikation, Implementierung, Verifikation, Hardstop.

---

## 11. Sprint-Empfehlungen (Solo-Dev, je 1–2 Tage)

| Sprint | Slices | Endzustand |
|---|---|---|
| **Sprint Doku-Sync** | M9.7 (= dieser Slice) | AGENTS.md/CLAUDE.md/PLAN.md/STATUS.md/heuristic auf realen Code-Stand. |
| **Sprint 1** | M9.6 (Prod-Smoke) | CI grün gegen den Proxy-Stack auf `main`/Tags/manuell; PR-Trigger vor Release neu bewerten. |
| **Sprint 2** | M10.1 + M10.2 (CVE-Monitor + Hardstop) | Wöchentlicher Audit, Hardstop-Datum aktiv. |
| **Sprint 3** | M10.4 (Auth-ADR) + M10.5 (Rate-Limits) | v1.0-Auth-Scope steht, Rate-Limits aktiv. |
| **Sprint 4** | M11.1 + M11.2 + M11.3 (Test-Härtung) | Coverage sichtbar, Evidence-Gate hart. |
| **Sprint 5** | M11.4 + M11.5 (E2E + Komplexität) | Browser-Smoke + Komplexitäts-Gate. |
| **Sprint 6+** | M12 (Hotspots + Feature-Welle) | v1.0-Releasekandidat. |
| **Sprint 7+** | M13 (v1.0-Vorbereitung) | Tag, SBOM, License-Report, AGPL-UI. |

---

## 12. Allgemeine Rollback-Heuristik

1. Jeder Slice läuft auf eigenem Feature-Branch (`feat/`, `fix/`, `chore/`, `refactor/`).
2. **Pflicht-Gate** für M10+: M9.6 muss fuer `main`/Tags/manuell grün sein; fuer Release-Kandidaten PR- oder RC-Smoke reaktivieren.
3. **3 grüne `main`-Runs** sind Pflicht, bevor ein Slice das Vertrauensmodell der Pipeline verändert (Beispiel: Auth-ADR-Implementierung, CVE-Hardstop-Aktivierung).
4. Doku-Slices sind reversibel ohne Code-Risiko; trotzdem `git mv` rückwärts dokumentieren.
5. **Bei Eval-Drift** in M12.1: Refactor sofort revertieren, kein Hotfix-Patching.

---

## 13. Abnahme-Checkliste „Doku-Sync 2026-05-04 erfolgreich"

Alle gleichzeitig erfüllt (für diesen Slice):

- [ ] `grep "v0.6.0" AGENTS.md` leer.
- [ ] `grep "Sub-Slice 19.*Workaround" CLAUDE.md` leer.
- [ ] `grep "F1.*offen\|F3.*offen" PLAN.md` leer (nur in historischen Sektionen geduldet).
- [ ] `docu/STATUS.md` „Aktive Slices" zeigt M9.6/M10.1/M10.4 statt F1/F2/F3.
- [ ] `docu/plan.heuristic.md` existiert.
- [ ] User-Drop-Files unter `docu/history/2026-05-04-*.md` archiviert.
- [ ] `npm run check` grün (oder explizit nicht ausgeführt = nur Doku, keine Code-Änderung).
- [ ] CHANGELOG `[Unreleased]` Eintrag.
