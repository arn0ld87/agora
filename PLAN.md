# Agora — Konsolidierter Findings- & Maßnahmenplan

**Stand:** 2026-05-03  
**Repo:** [`arn0ld87/agora`](https://github.com/arn0ld87/agora) · v0.9.0 (Tag) + Layer 0–6 Reader-Honesty-Refactor auf `main`  
**Quellen:** GitHub-ZIP (Stand 2026-05-03), GitIngest-Dump, Deep-Research-Voranalyse, vorhandene `PLAN.md` + Slash-Commands + Subagents im Repo  
**Ziel:** Findings aus Code-Review, Voranalyse und internem Backlog konsolidieren, mit den vorhandenen Slash-Commands (`/agora-next-task`, `/verify-after-subagent`, `/fix-task-*`) und Subagents (`agora-refactor-worker`, `agora-test-worker`, `agora-frontend-worker`, `agora-doc-worker`, `agora-evidence-auditor`) kompatibel halten und in eine umsetzbare Reihenfolge bringen.

---

## Methodik

1. Repo-Struktur, Konfiguration, CI, Doku-Korpus und Slash-Command-Vertrag gegen Code verifiziert (`grep`, `wc -l`, Modulgrößen).
2. Ist-Stand der vorhandenen `PLAN.md` (Tasks 01–34, Layer 0–10) und der `CLAUDE.md`-Layer-Tabelle akzeptiert — keine doppelten Einträge.
3. Deep-Research-Befunde nur dort übernommen, wo sie entweder am Code verifizierbar oder durch interne Doku gestützt sind.
4. Findings strikt **layer-aufwärts** sortiert. Hot-Spots aus Layer 0–6 sind code-verifiziert grün und werden **nicht** als offen geführt (Verifikationskommandos siehe `/verify-after-subagent`).

**Code-verifizierter Ist-Stand (nicht mehr offen):**

- `grep -rn '"schema_version": 1' backend/app/` → leer
- `grep -rn 'future prediction|rehearsal of the future|god.s eye view' backend/app/services/` → leer
- `grep -rn 'deepcopy(global_items\[:2\])' backend/app/services/` → leer
- `backend/app/contracts/__init__.py` exportiert alle 17 Contract-Klassen inkl. `RunSummary`/`RunDetail`/`RunsListResponse` (Sub-Slice 33 ist drin)
- `frontend/src/composables/` ist zu **10 von 10** TypeScript (#72 abgeschlossen)
- 41 TS-Dateien vs. 13 JS-Dateien im Frontend; **Layer 6 (#73) ist nicht abgeschlossen**, Hot-Spots: `main.js`, `router/index.js`, `utils/markdown.js`, `components/graph/graphPanel*.js`

---

## Kurzübersicht der wichtigsten Probleme

| ID | Cluster | Schweregrad | Ein-Satz-Befund |
|---|---|---|---|
| **F1** | Deployment / Prod | **hoch** | Kein lauffähiger Reverse-Proxy-Default im Repo (Issue #106), Prod-Pfad nicht end-to-end reproduzierbar. |
| **F2** | Auth / Security-Architektur | **hoch** | `VITE_AGORA_TOKEN` einkompiliert Bearer-Token ins Frontend-Bundle; `?token=`-Fallback noch im Code. Kein echtes Session-/Rollenmodell. |
| **F3** | Runtime / Skalierung | **hoch** | Gunicorn läuft mit **sync** Workern + `--timeout 600` (Workaround Sub-Slice 19); SSE/LLM-Streams blockieren Worker. `gevent` ist als Dep schon im `pyproject.toml`, aber nicht im `CMD`. |
| **F4** | CVE-Watchlist | **hoch** | 6 ignorierte CVEs (`pip-audit --ignore-vuln`), Frist **2026-07-30** — durch harte Upstream-Pins von `camel-ai`/`camel-oasis`/`sentence-transformers` blockiert. |
| **F5** | Doku- & Versions-Drift | **mittel** | README sagt 1383 Tests / Layer 0–5; `CLAUDE.md` sagt 1289+141 Tests / Layer 0–6. `pyproject.toml`/`package.json` weiter `0.9.0`, `main` post-tag ohne neuen Marker. ROADMAP nennt noch v0.6.1. |
| **F6** | Test-Qualität | **mittel** | Keine Coverage-Messung, keine `--cov-fail-under`-Schwelle, keine E2E-Suite. `evidence-quality`-Gate läuft mit `--soft`. |
| **F7** | Code-Hotspot Backend | **mittel** | `report_agent.py` mit **2400 LOC** trotz Refactor (-31,6 % seit v0.9.0) der größte Knoten; `simulation_runner.py` 1904 LOC, `oasis_profile_generator.py` 1502 LOC, `graph_tools.py` 1492 LOC. |
| **F8** | Code-Hotspot Frontend | **mittel** | `Step2EnvSetup.vue` 1804 LOC, `Step4Report.vue` 1287 LOC, `Step3Simulation.vue` 877 LOC — Komponenten sind nach den Refactors weiter Multi-Concern. |
| **F9** | Layer-7 Feature-Backlog | **mittel** | Compare-Kette (#65/#66/#67), Graph-Diff-API (#74), Compare-UI (#76) — Specs/Spikes da, Code-Schnitt offen. |
| **F10** | Layer-8 Persona-Review-UX | **mittel** | Persona-Diff (#69) und Approve/Reject/Regenerate (#70) noch offen, blockieren Persona-Review-Reife. |
| **F11** | Layer-6 Frontend-TS-Reste | **niedrig** | 13 `.js`-Dateien im Frontend (Composables-Migration läuft, `#73` Kritische Features noch nicht final). |
| **F12** | Lint-Tiefe / Komplexitäts-Gates | **niedrig** | Backend-`ruff.lint.select = ["E","F"]` ist Syntax-Gate, kein Design-Gate. Keine Komplexitäts-/Duplikat-Messung in CI. |
| **F13** | Wissens-Fragmentierung in `docu/` | **niedrig** | 130+ Arbeitsprotokolle plus mehrere konkurrierende Plan-Dateien (`PLAN.md`, `REFACTORING_PLAN.md`, `SECURITY_REVIEW.md`, `docu/codex_plan.md`, `docu/feature-roadmap.md`, `docu/refactoring-backlog-priorisiert.md`) — keine Single Source of Truth. |
| **F14** | AGPL-Compliance-Operationalisierung | **niedrig** | Lizenz korrekt, aber kein „Source-available“-Pfad in der laufenden App, kein SBOM, kein Third-Party-License-Report. |

---

## Findings im Detail

Reihenfolge: Schweregrad absteigend, innerhalb gleicher Schweregrad Layer-Bottom-Up.

### F1 — Reverse-Proxy-Default fehlt (Issue #106)

| Feld | Wert |
|---|---|
| Kategorie | Deployment / Ops |
| Schwere | **hoch** |
| Layer | 9 |
| Issue / Task | #106 / Task 33 |
| Subagent | `agora-refactor-worker` (Sonnet) + `agora-doc-worker` (Haiku) |

**Befund.** `docker-compose.prod.yml` setzt einen externen Reverse-Proxy voraus (Backend bindet `127.0.0.1:5001`, Frontend-Vite-Port entfällt per `!override`), aber das Repo liefert kein lauffähiges Beispiel. Das `prod-builder`-Stage im Dockerfile baut zwar das Frontend-Bundle, aber Gunicorn serviert es nicht und es gibt keinen Sidecar-Nginx im Repo.

**Lösungsschritte:**

1. Neue Datei `deploy/nginx/agora.conf` mit `/` → statisch aus `frontend/dist`, `/api/*` → `proxy_pass http://agora:5001`, `/api/simulation/*/stream` → `proxy_buffering off; proxy_read_timeout 600s`.
2. Neue Datei `deploy/compose/docker-compose.prod-with-proxy.yml` (Sidecar-Variante mit `nginx:alpine`, Bind-Mount auf `frontend/dist` und Conf, Backend-Port nicht mehr publishen).
3. `docu/deployment-prod-like.md` erweitert um konkrete Block-Beispiele für **Sidecar-Nginx**, **Traefik-Labels** und **Tailscale-Funnel** (jeweils 1 Section, gleiche Struktur).
4. `scripts/verify-deploy.sh` erweitern: nach `docker compose up -d` ein `curl -fsS http://localhost/health` gegen Proxy-Port, nicht direkt gegen `:5001`.
5. CI-Job `docker-image.yml` smoket den Proxy-Stack, nicht nur den Backend-Container.

**Akzeptanz:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml -f deploy/compose/docker-compose.prod-with-proxy.yml up -d` liefert eine produktionsähnliche Topologie aus dem Repo heraus, ohne dass der Operator externe Conf-Files schreiben muss. `Closes #106`.

---

### F2 — Auth-Modell ist Single-User-Token, im Bundle einkompiliert

| Feld | Wert |
|---|---|
| Kategorie | Security |
| Schwere | **hoch** |
| Layer | 9 (Prod-Hardening), greift in 0/1 |
| Issue / Task | (neu — bisher kein dediziertes Issue, in `SECURITY_REVIEW.md` F2 dokumentiert) |
| Subagent | `agora-refactor-worker` + `agora-frontend-worker` |

**Befund.** Drei reale Probleme stapeln sich:

1. `Dockerfile` `prod-builder`-Stage zieht `VITE_AGORA_TOKEN` als Build-Arg in das **Frontend-Bundle als Plaintext** (Code-Kommentar: „Nur sinnvoll für Single-User-Tailnet-Deploys; nicht für Public-Internet"). Wer das Bundle hat, hat den Token.
2. `?token=`-Query-Fallback ist im Code als Deprecation-Pfad noch aktiv (`backend/app/utils/auth.py::_extract_token`), Token landet damit potentiell in Proxy-Logs / Browser-History.
3. Das Token ist ein **Shared Secret**, kein User-Modell — kein Logout, kein Audit, keine Rotation-Policy außer „Container neu bauen".

**Lösungsschritte (3 Slices):**

1. **S2.1 — Build-Arg deprecaten** (S, sofort, `agora-refactor-worker`):
   - `Dockerfile`: `VITE_AGORA_TOKEN`-Block hinter `ARG ALLOW_BUILD_TIME_TOKEN=false` gaten; bei `false` (Default) wird `VITE_AGORA_TOKEN=""` injiziert und das Frontend muss den Token zur Laufzeit abfragen.
   - `frontend/src/api/index.ts`: bei leerem Bundle-Token einen Login-Flow gegen `POST /api/auth/ticket` triggern (Token per `prompt()` oder dedizierter Login-View, in `localStorage` cachen).
   - `docu/security-hardening.md` aktualisieren: alter Pfad steht nur noch als Single-User-Tailnet-Override mit explizitem Build-Befehl drin.
2. **S2.2 — `?token=` in Prod hart deaktivieren** (S, `agora-refactor-worker`):
   - `backend/app/utils/auth.py::_extract_token`: bei `Config.DEBUG=False` und `?token=` → `403` mit `code: "query_token_disabled_in_prod"`. SSE/Downloads müssen Signed Tickets nutzen (Pfad existiert seit P0.2).
   - Frontend: `stream.ts` darf `?ticket=` weiter setzen, **niemals** `?token=`. Test-Canary in `tests/test_signed_ticket.py` ergänzen.
3. **S2.3 — Session/Cookie-Modell vorbereiten** (M, Spike + Doku, `agora-doc-worker`):
   - ADR `docu/decisions/0001-session-modell.md`: Trade-off zwischen Flask-Login + HttpOnly-Cookie vs. weiter mit Bearer + Refresh-Tickets.
   - **Kein** Code in diesem Slice — Spike + Entscheidung. Implementierung ist v1.0-Material.

**Akzeptanz:** S2.1 + S2.2 als zwei getrennte PRs, nach Merge ist `grep -rn 'VITE_AGORA_TOKEN' frontend/src/` leer und ein Test pinnt das `403` für `?token=` in Non-Debug.

---

### F3 — Gunicorn sync-Worker + 600s Timeout

| Feld | Wert |
|---|---|
| Kategorie | Runtime / Skalierung |
| Schwere | **hoch** |
| Layer | 9 |
| Issue / Task | (Workaround Sub-Slice 19; saubere Lösung Plan in `docu/2026-04-29-prod-slice2-gunicorn.md`) |
| Subagent | `agora-refactor-worker` + `agora-test-worker` |

**Befund.** `Dockerfile` Z. 96 ff.: `gunicorn --workers 2 --timeout 600 --graceful-timeout 30`. `gevent` ist als Dep schon vorhanden (`pyproject.toml`), aber nicht im `CMD`. Bei laufendem Report-Agent oder Ontology-Generation blockt jeder Sync-Worker den Request bis 600 s — bei 2 Workern reicht ein zweiter Long-Run, um Health-Checks ins Timeout zu treiben. Der SSE-Endpoint `/api/simulation/<id>/stream` ist bei Sync-Workern grundsätzlich problematisch.

**Lösungsschritte:**

1. `Dockerfile` `prod`-Stage `CMD` ändern auf `-k gevent --workers 2 --worker-connections 1000 --timeout 120 --graceful-timeout 30`.
2. **Fork-Safety prüfen** (`agora-test-worker`): neue Tests in `tests/test_gunicorn_compat.py`, die Neo4j-Connection-Pool und Redis-Connection-Pool **nach Fork** instantiieren (Pattern: `multiprocessing.Process` als Fork-Surrogat). Bei aktuellem Code-Stand ist `Neo4jStorage` als Singleton im DI-Container — der Pool muss per `os.register_at_fork` resettet werden.
3. **OASIS-Subprozess** unter gevent-Monkey-Patching smoken: `tests/integration/test_oasis_under_gevent.py` startet eine 1-Round-Sim und prüft, dass `subprocess.Popen` nicht durch Monkey-Patch blockiert (gevent patcht standardmäßig `subprocess`).
4. CI-Job `contract-gates.yml` um `prod-runtime-smoke` erweitern: `docker compose -f ... -f docker-compose.prod.yml up -d`, dann `curl -fsS /health` in Schleife mit konkurrierendem Long-Request.
5. Doku: `docu/2026-04-29-prod-slice2-gunicorn.md` von „Plan" auf „umgesetzt" heben + Caveat-Liste.

**Akzeptanz:** Prod-Container hält 50 Concurrent-SSE-Streams aus, Health-Check antwortet < 500 ms während Long-Run, alle Backend-Tests grün.

---

### F4 — CVE-Watchlist mit Frist 2026-07-30

| Feld | Wert |
|---|---|
| Kategorie | Security / Dependency |
| Schwere | **hoch** (Frist!) |
| Layer | 10 |
| Issue / Task | #121–#126 / Task 34 |
| Subagent | `agora-evidence-auditor` (Read-only-Audit) + `agora-doc-worker` |

**Befund.** Sechs CVEs mit `--ignore-vuln` in `.github/workflows/ci.yml`, Frist **alle 2026-07-30**. Pinning-Sources: `camel-ai==0.2.78`, `camel-oasis==0.2.5`, `sentence-transformers==3.0.0`. Risiko ist real (Pillow-CVEs sind RCE-Klassen, transformers-CVE in NLP-Tokenizer).

**Lösungsschritte (parallel zu Feature-Arbeit, nicht blockierend):**

1. **Wöchentlicher pip-audit-Job** (S, sofort): neuer Workflow `cve-monitor.yml` (cron `0 6 * * 1`), läuft `pip-audit` ohne `--ignore-vuln` und kommentiert betroffene Issues automatisch — sichtbar machen, wann ein Upstream-Release durchgereicht wird.
2. **Upstream-Tracking verschärfen** (XS, `agora-doc-worker`): `docu/dependency-risk-register.md` bekommt eine Spalte „Upstream-Release-Watch" mit Link auf `camel-ai/releases`, `camel-oasis/releases`, `sentence-transformers/releases`. Cron-Job kann das später automatisch befüllen.
3. **Fork-Strategie als Eskalation** (M, Spike): wenn bis 2026-06-30 (also 30 Tage vor Frist) kein Upstream-Release: ADR `docu/decisions/0002-camel-fork-eskalation.md` mit Optionen (a) Vendoring, (b) Soft-Fork mit Patch-Ringen, (c) Replacement durch `langgraph`/eigener Subprozess. **Kein vorzeitiger Fork** — Aufwand-Nutzen-Verhältnis erst nach Frist klar.
4. **Hardstop** in `cve-monitor.yml`: am 2026-07-30 09:00 UTC schaltet der Job auf `--strict` ohne `--ignore-vuln` — wenn Upstream nicht released hat, wird CI rot und der Eskalations-ADR muss greifen.

**Akzeptanz:** Watchlist hat aktiven Owner, automatisches Tracking, klaren Hardstop. **Kein blindes Dependency-Upgrade** gegen harte Pins.

---

### F5 — Doku- und Versions-Drift

| Feld | Wert |
|---|---|
| Kategorie | Doku / Release-Hygiene |
| Schwere | **mittel** |
| Layer | quer (Meta) |
| Issue / Task | (neu) |
| Subagent | `agora-doc-worker` |

**Befund.** Quellen sind verteilt und widersprüchlich:

- `pyproject.toml` v0.9.0, `frontend/package.json` v0.9.0, `package.json` v0.9.0 → ok
- README: „1383 Tests grün (1258 Backend + 125 Frontend)"
- CLAUDE.md: „Backend 1289 Tests, Frontend 141 Tests"
- CHANGELOG `[Unreleased]`: spricht von 1283 Backend
- `docu/ROADMAP.md`: Header sagt „Current State (v0.6.1)" — **Stand 2026-04-27**, also 6 Tage vor letztem Commit
- `PLAN.md` (Repo-Root): „Tasks 01–17 plus 18–34" (konsistent zu Slash-Commands)
- `docu/feature-roadmap.md`, `docu/refactoring-backlog-priorisiert.md`, `REFACTORING_PLAN.md` (Root) — alle drei mit überlappendem Inhalt, unterschiedlichen Ständen.

**Lösungsschritte:**

1. **Zahlen-Quelle vereinheitlichen** (S): neues Script `scripts/sync-status.sh`, das Test-Counts aus dem letzten CI-Run zieht (oder lokal aus `pytest --collect-only -q | tail -1`) und in **einer** Datei `docu/STATUS.md` aktualisiert. README, CLAUDE.md, ROADMAP referenzieren `STATUS.md`, kopieren keine Zahlen mehr.
2. **ROADMAP aktualisieren** (S, `agora-doc-worker`): `docu/ROADMAP.md` auf v0.9.0 + Layer-Status (Layer 0–6 grün, Layer 7–10 in Arbeit) heben. Klare „Current / Next / Later"-Struktur, die direkt auf die Layer-Tabelle in `CLAUDE.md` verweist.
3. **Plan-Konsolidierung** (M): klare Rolle pro Datei — `PLAN.md` ist die operative Task-Quelle für Slash-Commands, `docu/refactoring-backlog-priorisiert.md` ist der historische Audit-Snapshot, `docu/feature-roadmap.md` und `REFACTORING_PLAN.md` (Root) werden nach `docu/history/` verschoben mit Header-Hinweis.
4. **Release-Marker** (S): nach jeder substanziellen `main`-Iteration einen `0.9.x-dev`-Tag setzen (`scripts/release.sh patch --dev`), damit `git describe` einen sinnvollen Wert liefert.
5. **CONTRIBUTING.md** (S): kurze Datei am Repo-Root mit „Wie arbeite ich hier mit?" — verweist auf `CLAUDE.md` für Agent-Workflows und `AGENTS.md` für Codex.

**Akzeptanz:** README, CLAUDE.md, ROADMAP zeigen identische Test-/Status-Zahlen. `docu/` ist auf eine klare Vorderbühne (`PLAN.md`, `STATUS.md`, `ROADMAP.md`) und Hinterbühne (`docu/history/`, `docu/decisions/`, `docu/logs/`) entzerrt.

---

### F6 — Test-Qualität: keine Coverage, keine E2E, soft Evidence-Gate

| Feld | Wert |
|---|---|
| Kategorie | Tests / CI |
| Schwere | **mittel** |
| Layer | 5 (Eval) + 1 (Tests sind Spec) |
| Issue / Task | (neu, indirekt #75/#105) |
| Subagent | `agora-test-worker` (Sonnet) |

**Befund.**

- `backend/pyproject.toml` `[tool.pytest.ini_options]` hat keine `--cov`-Opts, kein `pytest-cov` als Dep.
- `frontend/package.json` `test` läuft `vitest run`, kein `--coverage`.
- `.github/workflows/contract-gates.yml` Job `evidence-quality` läuft mit `--soft` (Kommentar: „bis Layer 5 fertig ist"). Layer 5 ist laut CLAUDE.md grün → der Soft-Schalter sollte fallen.
- Keine E2E-Suite (Playwright/Cypress) im Repo, ROADMAP nennt das als v1.0-Ziel.

**Lösungsschritte:**

1. **Coverage Backend** (S, `agora-test-worker`):
   - `pytest-cov` zu Dev-Deps.
   - `pyproject.toml` `addopts = "-ra --tb=short --import-mode=importlib --cov=app --cov-report=term-missing --cov-fail-under=70"`.
   - **Wichtig:** Schwelle anfangs 70 %, nicht 85 % — sonst kippt CI sofort. `app/services/`-Coverage messen und in `docu/STATUS.md` veröffentlichen, dann monatlich um 2 Punkte heben.
2. **Coverage Frontend** (S, `agora-test-worker`):
   - `@vitest/coverage-v8` zu DevDeps.
   - `package.json`: `"test:coverage": "vitest run --coverage"`, `"check": "vue-tsc --noEmit && npm run test:coverage && npm run build"`.
   - Schwelle 60 % anfangs (Vue-SFCs sind schwerer zu testen, viele UI-Pfade).
3. **`evidence-quality` hart schalten** (S, `agora-test-worker`):
   - `.github/workflows/contract-gates.yml`: `--soft` raus, Schwellen aus `tests/eval/expected_metrics.json` als Hard-Gate (Snapshot-Pin existiert seit Sub-Slice 17).
4. **E2E-Spike** (L, neuer Slice, `agora-test-worker`):
   - `frontend/e2e/` mit Playwright (`@playwright/test`).
   - **Genau 3 Tests** zum Start: (a) Health + Login, (b) Upload + Graph-Build, (c) Persona-Review-Approval-Flow + Sim-Start. Nicht mehr — sonst wird E2E zur Wartungslast.
   - Eigener CI-Workflow `e2e.yml`, läuft gegen `docker compose up -d`, nightly + on-demand-Label `run-e2e`.

**Akzeptanz:** `npm run check` zeigt Coverage. `pytest` failt bei < 70 %. `evidence-quality` bricht hart bei Drift. E2E grün auf nightly.

---

### F7 — `report_agent.py` mit 2400 LOC (und weitere Backend-Hotspots)

| Feld | Wert |
|---|---|
| Kategorie | Code-Qualität / Architektur |
| Schwere | **mittel** |
| Layer | 1/3 (fachlich Reader-Honesty) |
| Issue / Task | (neu, EPIC-07-Folge) |
| Subagent | `agora-refactor-worker` |

**Befund.** Trotz Refactor (-31,6 % seit v0.9.0) ist `report_agent.py` mit 2400 LOC der größte Knoten. Dort laufen Prompt-Templating (eigentlich `report_prompts.py`-Re-Export), Section-Building, Claim-Atomisierung, Evidence-Binding, Tool-Result-Handling, Provenance-Anker, Confidence-Berechnung, ReACT-Loop und Section-Dedup zusammen. Weitere Hot-Spots:

| Modul | LOC | Konzern |
|---|---:|---|
| `services/report_agent.py` | 2400 | Section-Builder + Claim-Atomisierung + ReACT-Loop |
| `services/simulation_runner.py` | 1904 | OASIS-Subprozess-Mgmt + Eventbus + State-Sync |
| `services/oasis_profile_generator.py` | 1502 | Persona-LLM-Prompts + Quoten + Voice-Register |
| `services/graph_tools.py` | 1492 | 4 Tool-Implementierungen (Quick/Panorama/Insight/Interview) |
| `services/simulation_config_generator.py` | 1044 | Config-Bauer + Validation |

**Lösungsschritte (Slice-by-slice, nicht Big-Bang):**

1. **`report_agent.py` weiter zerlegen** (M, `agora-refactor-worker`):
   - `services/report/section_builder.py` — `_build_section`, `_attach_provenance`, Time-Series-Sampling.
   - `services/report/claim_mapper.py` — Claim-Atomisierung, supports_claim-Logik.
   - `services/report/react_loop.py` — `_run_react_loop`, Tool-Limit-Logik.
   - `services/report_agent.py` bleibt als Façade (Public-API), delegiert. Re-Export-Pattern wie schon bei `neo4j_storage.py` angewendet.
   - Pflicht: kein Verhalten ändert sich. Tests müssen vorher grün sein, nach Refactor grün sein. Snapshot-Tests aus `tests/eval/` sind die Sicherung.
2. **`simulation_runner.py` schneiden** (M):
   - `services/sim/process_manager.py` — `Popen`-Lifecycle, Signal-Handling.
   - `services/sim/event_sync.py` — Eventbus-Bridge, RPC-Race-Logik.
   - `simulation_runner.py` als Façade.
3. **Komplexitäts-Gate als Pflicht** (S, voraussetzung für 1+2):
   - `radon` zu Dev-Deps; `scripts/check_complexity.sh` läuft `radon cc -nc` und failt bei > C-Klasse.
   - Neue CI-Stufe in `contract-gates.yml`: `complexity-gate`.
   - Schwelle: keine neuen Funktionen mit Cyclomatic > 15 (bestehende werden geduldet, Allow-List in `radon.cfg`).

**Akzeptanz:** `report_agent.py` < 1200 LOC, alle Tests grün, Snapshot-Eval-Metriken unverändert. CI-Komplexitäts-Gate grün ohne neue Allow-List-Einträge.

---

### F8 — `Step2EnvSetup.vue` 1804 LOC, `Step4Report.vue` 1287 LOC

| Feld | Wert |
|---|---|
| Kategorie | Code-Qualität Frontend |
| Schwere | **mittel** |
| Layer | 4 |
| Issue / Task | (neu, EPIC-03/EPIC-14-Folge) |
| Subagent | `agora-frontend-worker` |

**Befund.** Trotz `useWorkspaceMode`/`useWorkspaceStatus`/`useGraphRender`-Composables sind die zwei Hauptviews zu groß: `Step2EnvSetup.vue` enthält Quoten-Editor, Persona-Review-UI und LLM-Modell-Auswahl in einer Datei; `Step4Report.vue` enthält Section-Render, Confidence-Badges, Evidence-Drawer, Export-Center und Sticky-Scroll-Logik in einer Datei.

**Lösungsschritte:**

1. **`Step2EnvSetup.vue` aufteilen** (M, `agora-frontend-worker`):
   - `frontend/src/components/step2/QuotaPlanEditor.vue` — Quoten-UI aus Sub-Slice 20c.
   - `frontend/src/components/step2/PersonaReviewPanel.vue` — Review-UI aus Sub-Slice 02 / Issue #69 Vorbereitung.
   - `frontend/src/components/step2/ModelPicker.vue` — Modell-Wahl + Voice-Register-Override.
   - `Step2EnvSetup.vue` orchestriert nur noch (Routing zwischen Tabs).
2. **`Step4Report.vue` aufteilen** (M):
   - `frontend/src/components/step4/SectionRenderer.vue` — Section-Body + ConfidenceBadge + EvidenceDrawer.
   - `frontend/src/components/step4/ExportCenter.vue` — JSON/MD/CSV/PDF-Export.
   - `frontend/src/components/step4/LogsPane.vue` — Sticky-Scroll-Logs (Sub-Slice 30 nutzt schon `useStickyScroll`).
3. **TS-Migration in einem Aufwasch** (S, opportunistisch): die neuen Datei kommen nicht mehr als `.vue`+`<script>` JS, sondern als `.vue`+`<script setup lang="ts">` mit Zod-getypten Props (`reportContract.ts`, `personaQuotaContract.ts`).

**Akzeptanz:** Keine Vue-Datei in `frontend/src/components/Step*.vue` > 800 LOC. Bestehende Vitest-Specs (`Step4Report.spec.ts`, `Step2EnvSetup.spec.ts`) grün, ggf. um Smoke-Tests gegen die neuen Sub-Komponenten erweitert.

---

### F9 — Layer-7 Feature-Backlog (Compare + Graph-Diff)

| Feld | Wert |
|---|---|
| Kategorie | Feature-Backlog |
| Schwere | **mittel** |
| Layer | 7 |
| Issue / Task | #65/#66/#67/#74/#76 → PLAN.md Tasks 22/23/24/25 |
| Subagent | `agora-refactor-worker` (API) + `agora-frontend-worker` (UI) |

**Befund.** Specs/Spikes sind im CHANGELOG bereits dokumentiert (`task-22-graph-diff-spike.md`, `task-23-compare-model-spike.md`), Datenmodell und API-Schnitte sind skizziert. Aber: keine Implementierung im Code. `RunsDashboard` (#63) ist laut CLAUDE.md ebenfalls noch offen.

**Lösungsschritte (gemäß PLAN.md Tasks 22–25, nicht ändern, nur Reihenfolge fixieren):**

1. **#74 Graph-Diff API + Modell** (L) → `agora-refactor-worker`. Pflicht-Reihenfolge **vor** #76 UI.
2. **#65 Vergleichsmodell** (S, `agora-doc-worker`, schon im Spike) → API-Schnitt finalisieren.
3. **#66 Compare API** (L) → `agora-refactor-worker` nach #65.
4. **#76 Diff/Confidence UI** (L) → `agora-frontend-worker` nach #66 + #74.
5. **#67 Compare UI für zwei Branches** (L) → `agora-frontend-worker` nach #66.
6. **#63 RunsDashboard** (L) → `agora-frontend-worker` (#62 Runs-API ist als Task 26 schon offen, aber Sub-Slice 33 hat /api/runs erweitert — also #63-Frontend ist tatsächlich der nächste Schritt).

**Akzeptanz:** je Issue ein PR, je PR ein Slice nach `/agora-next-task`-Konvention. Keine Sammel-PRs.

---

### F10 — Persona-Review-UX (Layer 8)

| Feld | Wert |
|---|---|
| Kategorie | Feature-Backlog |
| Schwere | **mittel** |
| Layer | 8 |
| Issue / Task | #69/#70/#137 → PLAN.md Tasks 29/30/32 |
| Subagent | `agora-frontend-worker` + `agora-refactor-worker` |

**Befund.** Persona-Review-Service-Backend ist da (`persona_review_service.py`, `persona_quality_service.py`), Sub-Slice 30 hat Sticky-Scroll geliefert. Was fehlt: **Persona-Diff gegen Entity-Kontext** (#69) und **Approve/Reject/Regenerate-Workflow** (#70) — das macht das Feature erst nutzbar. #137 (Graph-Build-Batch-Marker für Auto-Freeze) ist UI-Polish, kommt nach #69/#70.

**Lösungsschritte:**

1. **#69 Persona-Diff** (M, `agora-frontend-worker`):
   - Frontend-Composable `usePersonaDiff.ts` (vergleicht Persona-LLM-Output gegen Entity-Properties aus Neo4j).
   - UI in neuer `PersonaReviewPanel.vue` (siehe F8): pro Persona ein Diff-Panel mit Entity-Bezug.
   - Backend: `GET /api/personas/<id>/entity-context` liefert Entity-Properties zum Vergleich.
2. **#70 Approve/Reject/Regenerate** (L):
   - `POST /api/personas/<id>/approve|reject|regenerate` (existieren teilweise, müssen vereinheitlicht werden).
   - State-Machine: `pending → approved | rejected | regenerating → pending`.
   - UI: Action-Buttons im PersonaReviewPanel.
3. **#137 Batch-Marker** (M, `agora-refactor-worker`): kommt nach #69/#70.

**Akzeptanz:** Vor Sim-Start (`PERSONA_REVIEW_ENABLED=true`) kann jede Persona im UI inspiziert, gegen Entity-Kontext verglichen, freigegeben oder regeneriert werden. State-Machine-Tests in `tests/services/test_persona_review_service.py`.

---

### F11 — Layer-6 Frontend-TS-Reste

| Feld | Wert |
|---|---|
| Kategorie | Code-Qualität Frontend |
| Schwere | **niedrig** |
| Layer | 6 |
| Issue / Task | #73 → PLAN.md Task 21 |
| Subagent | `agora-frontend-worker` |

**Befund.** Composables sind zu 10 von 10 TS migriert (#72 grün). Es bleiben 13 `.js`-Dateien, davon kritisch: `frontend/src/main.js`, `frontend/src/router/index.js`, `frontend/src/utils/markdown.js`, `frontend/src/components/graph/graphPanelData.js`, `graphPanelGeometry.js`, `graphPanelUtils.js`, `edgeLabelI18n.js` plus 6 Test-Specs. **Vue-Files** sind weiter `<script>` ohne `lang="ts"` — das wird in F8 mitabgeräumt.

**Lösungsschritte:**

1. **Trivial-Migration** (S, `agora-frontend-worker`):
   - `main.js` → `main.ts` (1:1, type imports).
   - `router/index.js` → `router/index.ts` mit `RouteRecordRaw[]`-Typing.
   - `utils/markdown.js` → `utils/markdown.ts`.
2. **Graph-Helpers** (M):
   - `components/graph/graphPanelData.js` → `.ts` mit `D3SimulationNode`, `D3SimulationLink`-Types.
   - `graphPanelGeometry.js`, `graphPanelUtils.js`, `edgeLabelI18n.js` analog.
3. **Tests parallel migrieren** — Spec-Files folgen, sobald die getestete Datei TS ist.

**Akzeptanz:** `find frontend/src -name '*.js' -not -path '*/node_modules/*'` ≤ 3 (nur `vite.config.js`, `eslint.config.js` und ggf. ein Build-Script). #73 closed.

---

### F12 — Lint-Tiefe und Komplexitäts-Gates

| Feld | Wert |
|---|---|
| Kategorie | CI / Code-Qualität |
| Schwere | **niedrig** |
| Layer | 5 (Tooling) |
| Issue / Task | (neu) |
| Subagent | `agora-test-worker` |

**Befund.** `backend/pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F"]
ignore = ["E501"]
```

Das fängt Syntax und Imports, aber keine Komplexität, keine Refactor-Hinweise, keine Import-Ordnung, keine `mypy`-Checks (CLAUDE.md erwähnt `uv run mypy app`, aber kein Job in CI prüft das).

**Lösungsschritte:**

1. **Ruff erweitern** (S, `agora-doc-worker` für Doku, `agora-test-worker` für Fix-Welle):
   - `select = ["E", "F", "I", "B", "SIM", "PLR", "C90"]`
   - `[tool.ruff.lint.mccabe] max-complexity = 12`
   - **Erst** in einem dedizierten Slice ausrollen, sonst wird der erste PR ein 500-File-Diff. Pattern wie schon bei „default-strict ruff scope rollout".
2. **mypy als CI-Job** (S):
   - `mypy.ini` mit `strict_optional = True`, `disallow_untyped_defs = True` für `app/contracts/` und `app/api/` (Boundary-Module).
   - `.github/workflows/contract-gates.yml`: neuer Job `mypy-strict`.
3. **Komplexitäts-Gate** (siehe F7.3) — `radon` läuft als CI-Step.
4. **`jscpd` für Frontend** (S): Duplikat-Erkennung in `frontend/src/`, Schwelle 5 % Duplikat-Anteil. Häufige Duplikate (Status-Badges, Toast-Calls) auf gemeinsame UI-Atome heben.

**Akzeptanz:** `ruff check`, `mypy app/contracts app/api`, `radon cc -nc`, `jscpd frontend/src` laufen alle als CI-Gates.

---

### F13 — `docu/`-Fragmentierung

| Feld | Wert |
|---|---|
| Kategorie | Doku-Hygiene |
| Schwere | **niedrig** |
| Layer | quer |
| Issue / Task | (neu) |
| Subagent | `agora-doc-worker` |

**Befund.** `ls docu/ \| wc -l` → 130+ Dateien. Davon ~110 Arbeitsprotokolle, ~10 strategische Dokumente, ~10 sonstige (Logs, Plans). Mehrere konkurrierende Plan-Files (`PLAN.md` Root + `docu/feature-roadmap.md` + `docu/refactoring-backlog-priorisiert.md` + `REFACTORING_PLAN.md` Root + `docu/codex_plan.md` + `docu/plan_0.4.md` + `docu/2026-04-29-prod-setup-plan.md`). Für neue Contributors ist nicht klar, was die Quelle der Wahrheit ist.

**Lösungsschritte:**

1. **Verzeichnisstruktur fixieren** (S, `agora-doc-worker`):
   - `docu/decisions/` — ADRs (gibt's noch nicht, aber Skill-Vorlage in `agora-doc-worker.md`).
   - `docu/design/` — Design-Docs (existiert).
   - `docu/history/` — Arbeitsprotokolle, ältere Pläne (existiert).
   - `docu/logs/` — CI/Audit-Logs (existiert).
   - **Hauptbühne** auf 5 Dateien beschränken: `README.md`, `target-architecture.md`, `refactoring-backlog-priorisiert.md` (Audit-Snapshot), `ROADMAP.md`, `STATUS.md` (neu, aus F5).
2. **Arbeitsprotokoll-Migration** (M, automatisierbar): Script `scripts/move-protocols-to-history.sh` verschiebt `docu/2026-04-*-arbeitsprotokoll.md` und `docu/2026-05-*-arbeitsprotokoll.md` nach `docu/history/`. Aktuelles Protokoll bleibt nur in `[Unreleased]` referenziert.
3. **Plan-Konsolidierung** (siehe F5.3) — Root-Files `REFACTORING_PLAN.md`, `agora_*.md` (Stand 2026-04-2x) nach `docu/history/`.
4. **CONTRIBUTING.md** (siehe F5.5) — Top-Level-Datei mit „Welche Datei für was?".

**Akzeptanz:** `ls docu/ \| wc -l` ≤ 25 Top-Level-Files; alle Arbeitsprotokolle in `docu/history/`; eine `CONTRIBUTING.md` am Repo-Root.

---

### F14 — AGPL-Operationalisierung

| Feld | Wert |
|---|---|
| Kategorie | Recht / Compliance |
| Schwere | **niedrig** |
| Layer | quer |
| Issue / Task | (neu) |
| Subagent | `agora-doc-worker` |

**Befund.** Lizenz ist konsistent AGPL-3.0 (Root, Backend, README, LICENSE), Fork-Linie zu `nikmcfly/MiroFish-Offline` ist sauber. Aber: keine „Source-available"-Anzeige in der laufenden App, kein SBOM, kein Third-Party-License-Report. Bei AGPL-konformer Bereitstellung über Netzwerk wäre das Pflicht.

**Lösungsschritte:**

1. **UI-Footer-Hinweis** (XS, `agora-frontend-worker`): in `WorkspaceHeader.vue` oder neuer `AppFooter.vue` ein „Source: github.com/arn0ld87/agora · v0.9.0 · AGPL-3.0"-Link. Backend liefert `GET /api/version` mit Commit-SHA.
2. **SBOM** (S, `agora-doc-worker`): `cyclonedx-py` als Dev-Dep + CI-Job, der `sbom.cdx.json` in den Release-Artifacts ablegt. Frontend-SBOM via `cyclonedx-npm`.
3. **Third-Party-License-Report** (S): `pip-licenses --format=markdown > docu/THIRD-PARTY-LICENSES.md`, im CI nach `uv sync` regeneriert + `git diff --exit-code` als Drift-Check.

**Akzeptanz:** UI zeigt Source-Link + Version + SHA. SBOM ist Teil jeder Release. Third-Party-License-Report wird CI-gepflegt.

---

## Roadmap — logische Umsetzungsreihenfolge

Die Reihenfolge ergibt sich aus zwei Prinzipien:

1. **Layer-Bottom-Up bleibt verbindlich** (CLAUDE.md, PLAN.md, `/agora-next-task`).
2. **Risiko × Wirkung** zuerst — Prod-Deployability + Auth-Modell + Doku-Sync sind höhere Hebel als zusätzliche Features.

### Milestone M9 — Prod-Hardening (Mai 2026, ~2–3 Wochen)

> Fokus: das System für reale Single-Tenant-Deploys belastbar machen.

| # | Slice | Aufwand | Subagent | Bezug |
|---|---|---|---|---|
| 1 | F5 Doku-Sync (`STATUS.md`-Skript, ROADMAP-Update, `CONTRIBUTING.md`) | S+S | `agora-doc-worker` (Haiku) | F5 |
| 2 | F1.1 Reverse-Proxy-Sidecar (Nginx-Conf + Compose-Override + Doku) | M | `agora-refactor-worker` + `agora-doc-worker` | #106, F1 |
| 3 | F2.1 `VITE_AGORA_TOKEN` per `ARG` gaten + Frontend-Login-Flow | S | `agora-refactor-worker` + `agora-frontend-worker` | F2 |
| 4 | F2.2 `?token=` in Prod hart deaktivieren | S | `agora-refactor-worker` | F2 |
| 5 | F3 Gunicorn-Gevent-Migration + Fork-Safety-Tests | M | `agora-refactor-worker` + `agora-test-worker` | F3, Sub-Slice 19 |
| 6 | F1.2 `verify-deploy.sh` smoket Proxy-Stack | S | `agora-test-worker` | F1, F3 |

**Exit:** Repo liefert reproduzierbares Prod-Setup, Auth-Bundle-Pfad ist defaultmäßig zu, gevent-Worker laufen mit OASIS-Subprozess kompatibel.

### Milestone M10 — Test-Schärfe + CVE-Watch (Juni 2026, ~2 Wochen)

> Fokus: Qualitäts-Gates härten, CVE-Backlog aktiv überwachen.

| # | Slice | Aufwand | Subagent | Bezug |
|---|---|---|---|---|
| 7 | F6.1 Coverage Backend (`pytest-cov`, Schwelle 70 %) | S | `agora-test-worker` | F6 |
| 8 | F6.2 Coverage Frontend (`@vitest/coverage-v8`, Schwelle 60 %) | S | `agora-test-worker` | F6 |
| 9 | F6.3 `evidence-quality` `--soft` raus | S | `agora-test-worker` | F6, Sub-Slice 17 |
| 10 | F12 Ruff-Erweiterung + mypy-Strict-Job + Radon-Komplexitäts-Gate | M | `agora-test-worker` | F12 |
| 11 | F4.1 `cve-monitor.yml` (wöchentlich, ohne `--ignore-vuln`) | S | `agora-doc-worker` | #121–#126, F4 |
| 12 | F4.2 Dependency-Risk-Register-Erweiterung + Hardstop-Logik | S | `agora-doc-worker` | F4 |

**Exit:** CI-Gates sind hart, Coverage sichtbar, CVE-Watch aktiv mit klarer Eskalation.

### Milestone M11 — Code-Hotspots zerschneiden (Juni–Juli 2026, ~3 Wochen)

> Fokus: Wartbarkeit für die nächste Feature-Welle vorbereiten.

| # | Slice | Aufwand | Subagent | Bezug |
|---|---|---|---|---|
| 13 | F7.1 `report_agent.py` → `services/report/{section_builder,claim_mapper,react_loop}.py` | M | `agora-refactor-worker` | F7 |
| 14 | F7.2 `simulation_runner.py` → `services/sim/{process_manager,event_sync}.py` | M | `agora-refactor-worker` | F7 |
| 15 | F8.1 `Step2EnvSetup.vue` aufteilen (3 Sub-Komponenten) | M | `agora-frontend-worker` | F8, EPIC-03 |
| 16 | F8.2 `Step4Report.vue` aufteilen (3 Sub-Komponenten) | M | `agora-frontend-worker` | F8 |
| 17 | F11 TS-Migration der verbleibenden 13 `.js`-Dateien | S+M | `agora-frontend-worker` | #73, Task 21, F11 |

**Exit:** Kein Backend-Modul > 1500 LOC, keine Vue-Datei > 800 LOC, Frontend praktisch durchgängig TS.

### Milestone M12 — Feature-Welle Compare/Diff/Persona (Juli–August 2026, ~4–6 Wochen)

> Fokus: konkreter Produktwert — Branch-Vergleich, Persona-Review-UX, Runs-Dashboard.

| # | Slice | Aufwand | Subagent | Bezug |
|---|---|---|---|---|
| 18 | #74 / Task 22 Graph-Diff Modell + API | L | `agora-refactor-worker` | F9 |
| 19 | #66 / Task 24 Compare-API für Kernmetriken | L | `agora-refactor-worker` | F9 |
| 20 | #76 / Task 16b Diff-/Confidence-UI (nach #74+#66+#75) | L | `agora-frontend-worker` | F9 |
| 21 | #67 / Task 25 Compare-UI für zwei Branches | L | `agora-frontend-worker` | F9 |
| 22 | #63 / Task 27 RunsDashboard.vue | L | `agora-frontend-worker` | F9 |
| 23 | #69 / Task 29 Persona-Diff gegen Entity-Kontext | M | `agora-frontend-worker` + `agora-refactor-worker` | F10 |
| 24 | #70 / Task 30 Approve/Reject/Regenerate-Workflow | L | `agora-frontend-worker` | F10 |
| 25 | #64 / Task 28 Resume/Restart-Aktionen aus UI | M | `agora-refactor-worker` + `agora-frontend-worker` | F9 |
| 26 | #137 / Task 32 Graph-Build Batch-Marker + Auto-Freeze | M | `agora-refactor-worker` + `agora-frontend-worker` | F10 |

**Exit:** Layer 7 + Layer 8 grün laut CLAUDE.md-Tabelle. v1.0-Releasekandidat realistisch.

### Milestone M13 — v1.0-Vorbereitung (August–September 2026, ~3 Wochen)

> Fokus: Compliance, E2E, Doku-Endausbau.

| # | Slice | Aufwand | Subagent | Bezug |
|---|---|---|---|---|
| 27 | F6.4 E2E-Spike mit Playwright (3 Tests, nightly) | L | `agora-test-worker` | F6 |
| 28 | F13 Doku-Konsolidierung + Arbeitsprotokoll-Migration | M | `agora-doc-worker` | F13 |
| 29 | F14.1 UI-Source-Link + `/api/version` mit SHA | XS | `agora-frontend-worker` | F14 |
| 30 | F14.2 SBOM (cyclonedx) + Third-Party-License-Report | S | `agora-doc-worker` | F14 |
| 31 | F2.3 Spike + ADR Session/Cookie-Modell | M | `agora-doc-worker` | F2 |
| 32 | Release v1.0.0 (Tag, Release Notes, Changelog-Migration) | S | `agora-doc-worker` | (Release) |

**Exit:** v1.0-Release mit reproduzierbarem Deploy, hartem CI, dokumentierter Compliance, klarer Wartungsbasis.

---

## Slash-Command-Anbindung

Alle Findings sind **kompatibel** zur bestehenden `/agora-next-task`-Heuristik-Tabelle. Die F-IDs lassen sich direkt als Subaufgaben unter PLAN.md-Tasks 18–34 einreihen, ohne `.claude/commands/agora-next-task.md` umzuschreiben — der Command kann weiterhin Layer-Bottom-Up arbeiten.

| F-ID | Verwendet |
|---|---|
| F1, F3 | PLAN.md Task 33 (#106), Sub-Slice 19 (gunicorn) |
| F2 | neuer Layer-9-Slice, kein Issue offen, würde als Task 35 ergänzt |
| F4 | PLAN.md Task 34 (#121–#126) |
| F5, F13 | Quer, Doku-Worker-Slices |
| F6, F12 | erweitert PLAN.md Layer 5 / EPIC-01 |
| F7 | EPIC-07-Folge (`report_agent.py` weiter) |
| F8 | EPIC-03-Folge |
| F9 | PLAN.md Tasks 22–28 |
| F10 | PLAN.md Tasks 29, 30, 32 |
| F11 | PLAN.md Task 21 (#73) |
| F14 | neuer Layer-10-Slice (Compliance) |

**Empfehlung:** in `.claude/commands/agora-next-task.md` Schritt 2 den bereits dokumentierten Block aus `PLAN.md` Teil E.3 (Tasks 18–34) übernehmen, sobald Task 17 abgeschlossen ist (laut CLAUDE.md ist das bereits der Fall, aber der Command spiegelt das noch nicht). F2 + F14 als neue Tasks 35/36 anhängen.

---

## Hardstops (gelten weiterhin)

Übernommen aus PLAN.md Teil K, mit Erweiterung für die neuen Findings:

- Kein Sammel-PR über mehrere Layer.
- Kein `Closes #N`, wenn der Issue nur vorbereitet wurde.
- Kein Dependency-Upgrade gegen harte Third-Party-Pins ohne Testlauf (gilt explizit für F4).
- Kein Frontend-TypeScript-Big-Bang vor stabilen API-Schemas (Layer 0 ist stabil → F11 ist sicher).
- Kein Prod-Deployment-Slice zusammen mit Report-Refactor.
- Kein Auto-Fix-Loop nach rotem Verify. Fehler reporten, Worktree stehen lassen.
- **Neu:** Kein Big-Bang-Refactor an `report_agent.py` ohne Snapshot-Eval-Tests grün vor + nach (F7, abgesichert durch Sub-Slice 17 Eval-Suite).
- **Neu:** Kein gevent-Switch ohne Fork-Safety-Tests für Neo4j+Redis-Pools (F3).
- **Neu:** Kein Ruff-Regel-Bump als Sammel-Diff — gescopter Rollout wie beim ersten Default-Strict-Move (F12).

---

## Nächste Schritte (genau 3)

1. **F5 + F1.1 als ersten zusammenhängenden Slice** durchziehen — ROADMAP/STATUS-Sync **und** Reverse-Proxy-Sidecar liefern in einem PR den größten Wahrnehmungs- und Betriebs-Hebel. Dispatch via `/agora-next-task` mit `agora-doc-worker` für Doku, `agora-refactor-worker` für Compose/Conf.
2. **F3 als zweiten Slice**: gevent-Migration mit Fork-Safety-Tests. Voraussetzung: `agora-test-worker` schreibt zuerst Tests gegen das aktuelle Sync-Verhalten als Spec-Pin, dann `agora-refactor-worker` macht den `CMD`-Switch, dann `/verify-after-subagent`.
3. **F2.1 + F2.2 parallel zu F3**: Token-Bundle deaktivieren und `?token=` in Prod hart sperren — kein Worktree-Konflikt zu F3, da andere Module. Beide Slices als getrennte PRs, kein Sammel-Commit.

