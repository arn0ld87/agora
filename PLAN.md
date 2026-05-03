# Konsolidierter Plan — `arn0ld87/agora` offene Issues

**Stand:** 2026-05-03  
**Ziel:** offene GitHub-Issues konsolidieren, priorisieren und so in `PLAN.md` abbilden, dass die vorhandenen Claude-Slash-Commands weiter mit einer klaren Task-Quelle arbeiten können.  
**Quellen:** GitHub Issues `is:issue is:open`, vorhandene `.claude/commands/*`, angehängtes `PLAN.md`-Muster.

---

## Executive Summary

Im Repo sind aktuell **23 offene Issues** sichtbar.

Die technische Priorität ist eindeutig:

```text
Contracts → Evidence/Confidence → Strict Frontend → Migration → Feature-Backlog → Deploy/Security
```

**Entscheidung:**  
Tasks **01–17** bleiben kompatibel zur bestehenden Slash-Command-Logik. Die offenen GitHub-Issues werden als Tasks **18–34** ergänzt oder in bestehende Tasks gemappt. Dadurch kannst Du `/agora-next-task`, `/verify-after-subagent` und die vorhandenen `/fix-task-*`-Commands weiterverwenden, ohne sofort die ganze Automatisierung umzubauen. Ein Plan, der nicht alles zerlegt. Man gönnt sich ja sonst nichts.

---

## Teil A — Offene Issues, konsolidiert

| Issue | Titel | Cluster | Prio | Aufwand | Behandlung |
|---|---|---|---|---|---|
| #141 | Step4-Report-Logs auf Sticky-Scroll migrieren | UX/Frontend | P2 | S/M | nach Frontend-Testbasis, kleiner Slice |
| #137 | Graph-Build: Batch-Marker-Event für Auto-Freeze beim Aufbau | Graph/UX | P2 | M | nach Settings-/Graph-Basis |
| #126 | security: track ignored CVE-2025-64712 until upstream fix | Security | P3 | XS | Watchlist, Upstream-Pin abwarten |
| #125 | security: track ignored CVE-2024-46455 until upstream fix | Security | P3 | XS | Watchlist, Upstream-Pin abwarten |
| #124 | security: track ignored CVE-2026-1839 until upstream fix | Security | P3 | XS | Watchlist, Upstream-Pin abwarten |
| #123 | security: track ignored CVE-2025-71176 until upstream fix | Security | P3 | XS | niedrig, Test-Runner, nicht Prod-Runtime |
| #122 | security: track ignored CVE-2026-40192 until upstream fix | Security | P3 | XS | Watchlist, PDF/Vision relevant |
| #121 | security: track ignored CVE-2026-25990 until upstream fix | Security | P3 | XS | Watchlist, PDF/Vision relevant |
| #106 | Reverse-Proxy vor Prod-Container für statisches Frontend | Deployment | P1 | M | separater Deploy-Slice |
| #107 | Schema-Migration alter v1-Reports nach v2 | Report/Schema | P0 | M | nach Contract-Fix, eigener Migration-Slice |
| #105 | Contradiction-Detector für Confidence-Penalty | Report/Evidence | P0 | M/L | mit #75 zusammenziehen |
| #76 | EPIC-15-ST-03 — UI für Diff und Confidence | Frontend/Report | P1 | L | nach #74/#75/#105 |
| #75 | EPIC-15-ST-02 — Report Confidence Score | Report/Evidence | P0 | M | mit #105 + Contract-Validierung |
| #74 | EPIC-15-ST-01 — Graph Diff Modell und API | Graph/API | P1 | L | Vorbedingung für #76 |
| #73 | EPIC-14-ST-03 — Kritische Features schrittweise migrieren | Frontend/TS | P2 | XL | nach #71/#72 |
| #72 | EPIC-14-ST-02 — Composables zuerst migrieren | Frontend/TS | P1 | L | Vorarbeit für #73 |
| #71 | EPIC-14-ST-01 — Frontend API-Modelle in TypeScript | Frontend/Contracts | P0 | M | an Layer 0 Contracts hängen |
| #70 | EPIC-13-ST-03 — Approve / Reject / Regenerate Workflow | Persona Review | P2 | L | nach #69 |
| #69 | EPIC-13-ST-02 — Persona Diff gegen Entity-Kontext | Persona Review | P2 | M | Vorbedingung für #70 |
| #67 | EPIC-12-ST-03 — Compare UI für zwei Branches | Simulation Compare | P2 | L | nach #66 |
| #66 | EPIC-12-ST-02 — Compare API für Kernmetriken | Simulation Compare | P1 | L | nach #65 |
| #65 | EPIC-12-ST-01 — Vergleichsmodell definieren | Simulation Compare | P1 | S | Start für Compare-Feature |
| #64 | EPIC-11-ST-03 — Resume/Restart-Aktionen aus UI | Runs | P2 | M | nach #62/#63 |
| #63 | EPIC-11-ST-02 — Dashboard-View für Runs bauen | Runs | P1 | L | nach #62 |
| #62 | EPIC-11-ST-01 — Runs API evaluieren und ergänzen | Runs/API | P1 | M | Basis für #63/#64 |

---

## Teil B — Konsolidierte Task-Liste

### Layer 0 — Slash-Command-kompatible Contract-Basis

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 01 | Pydantic-v2-Contracts anlegen | Grundlage für #71 #75 #105 #107 | P0 | M | `backend/app/contracts/*` | `/fix-task-01-contracts` |
| 02 | Contracts in API/Report-Agent verdrahten + Schema-Drift fixen | #107 teilweise | P0 | M | `backend/app/api/report.py`, `backend/app/services/report_agent.py` | `/fix-task-02-wire-contracts` |
| 03 | JSON-Schema-Dump + CI-Gate | #71 Voraussetzung | P0 | S | `dump_schemas.py`, `.github/workflows/*` | `/agora-next-task` |
| 04 | Zod-Spiegel im Frontend | #71 teilweise | P0 | M | `frontend/src/contracts/*` | `/agora-next-task` |

### Layer 1 — Report Trust / Evidence

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 05 | `chat_json` auf strict-Schema-Mode mit Fallback | #75 #105 indirekt | P1 | M | `backend/app/utils/llm_client.py` | `/agora-next-task` |
| 06 | Persona-Quoten-Vertrag verdrahten | DACH-Persona-Qualität | P1 | M | `prepare_service.py`, `oasis_profile_generator.py` | `/agora-next-task` |
| 07 | Anti-Dekorations-Fix: kein `global_items[:2]` | Report-Honesty | P1 | S | `backend/app/services/report_agent.py` | `/fix-task-04-anti-dekoration` |
| 08 | Confidence-Kalibrierung + Contradiction-Penalty | #75 #105 | P0 | M/L | `confidence_calculator.py`, `evidence_binder.py` | `/agora-next-task` |

### Layer 2 — Prompt- und DACH-Semantik

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 09 | Prompt-Semantik fixen: Prediction → Scenario | intern | P1 | S | `backend/app/services/report_prompts.py` | `/fix-task-03-prompt-semantik` |
| 10 | DACH-Voice-Constraints in Personas | intern | P2 | M | `oasis_profile_generator.py`, `prompts/*` | `/agora-next-task` |
| 11 | Voice-Lint als CI-Check | intern | P3 | S | `backend/scripts/check_voice.py` | `agora-test-worker` |

### Layer 3 — Reader Honesty / Report-Verteidigung

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 12 | Original-Quotes mit Provenance-Anker | #75 #105 unterstützt | P1 | M | `report_agent.py` Section-Builder | `/agora-next-task` |
| 13 | Time-Series-Sampling + Section-Dedup | intern | P2 | M | `report_agent.py` | `/agora-next-task` |
| 14 | Cluster-Naming deterministisch | intern | P3 | S | `report_agent.py` Cluster-Logik | `/agora-next-task` |

### Layer 4 — Frontend strict + Confidence UI

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 15 | `Step4Report.vue` auf strict-Zod-Parse | #71 | P1 | M | `frontend/src/components/Step4Report.vue` | `agora-frontend-worker` |
| 16 | Diff/Confidence-UI | #76, abhängig von #74 #75 #105 | P1 | L | neue Vue-Components | `agora-frontend-worker` |

### Layer 5 — Eval + Migration

| Task | Titel | Issue | Prio | Aufwand | Pfade | Command |
|---|---|---|---|---|---|---|
| 17 | Baseline-Eval-Suite + Fixtures + Snapshot-Tests | #75 #105 | P2 | L | `backend/tests/eval/*` | `agora-test-worker` |
| 18 | v1→v2 Report-Migration fertigstellen | #107 | P0 | M | `backend/scripts/migrate_reports_v1_to_v2.py` | neuer Slice nach Task 02 |

### Layer 6 — Frontend TypeScript

| Task | Titel | Issue | Prio | Aufwand | Pfade | Reihenfolge |
|---|---|---|---|---|---|---|
| 19 | Frontend API-Modelle vollständig nach TypeScript migrieren | #71 | P0 | M | `frontend/src/api/*.ts` | nach Tasks 03/04/15 |
| 20 | Composables zuerst nach TypeScript migrieren | #72 | P1 | L | `frontend/src/composables/*.ts` | nach #71 |
| 21 | Kritische Vue-Features nach TypeScript migrieren | #73 | P2 | XL | Run-Dashboard, Graph, Simulation, Report | nach #72 |

### Layer 7 — Graph / Runs / Compare

| Task | Titel | Issue | Prio | Aufwand | Pfade | Reihenfolge |
|---|---|---|---|---|---|---|
| 22 | Graph-Diff Modell und API | #74 | P1 | L | `TemporalGraphService`, API Endpoint | vor #76 |
| 23 | Vergleichsmodell definieren | #65 | P1 | S | Doku + API-Schnitt | Start Compare-Kette |
| 24 | Compare API für Kernmetriken | #66 | P1 | L | `/api/simulation/compare` | nach #65 |
| 25 | Compare UI für zwei Branches | #67 | P2 | L | Frontend Side-by-side | nach #66 |
| 26 | Runs API evaluieren und ergänzen | #62 | P1 | M | `/api/runs` | Basis Runs-Kette |
| 27 | `RunsDashboard.vue` bauen | #63 | P1 | L | `RunsDashboard.vue` | nach #62 |
| 28 | Resume/Restart-Aktionen aus UI | #64 | P2 | M | UI + Backend Endpoint | nach #62/#63 |

### Layer 8 — Persona Review + UX

| Task | Titel | Issue | Prio | Aufwand | Pfade | Reihenfolge |
|---|---|---|---|---|---|---|
| 29 | Persona Diff gegen Entity-Kontext | #69 | P2 | M | Persona Review UI/API | vor #70 |
| 30 | Approve / Reject / Regenerate Workflow | #70 | P2 | L | Review Lifecycle | nach #69 |
| 31 | Step4-Report-Logs auf Sticky-Scroll migrieren | #141 | P2 | S/M | `useIncrementalLogPolling.js`, `Step4Report.vue` | kleiner UI-Slice |
| 32 | Graph-Build Batch-Marker-Event + Auto-Freeze | #137 | P2 | M | Build-Stream, `useGraphRender.js` | abhängig von Settings/#133 |

### Layer 9 — Production Deployment

| Task | Titel | Issue | Prio | Aufwand | Pfade | Reihenfolge |
|---|---|---|---|---|---|---|
| 33 | Reverse-Proxy vor Prod-Container | #106 | P1 | M | `docker-compose.prod.yml`, Traefik/Nginx-Doku | separater Deploy-Slice |

### Layer 10 — Security Watchlist

| Task | Titel | Issue | Prio | Aufwand | Pfade | Reihenfolge |
|---|---|---|---|---|---|---|
| 34 | Security-Watchlist konsolidieren + Upgrade-Check | #121 #122 #123 #124 #125 #126 | P3 | S | `pyproject.toml`, `uv.lock`, `pip-audit`-Doku | erst schließen, wenn Upstream-Pins gelöst sind |

---

## Teil C — Architektur-Reihenfolge

```text
Layer 0   Contract Backbone                     Tasks 01–04
Layer 1   Report Trust / Evidence                Tasks 05–08
Layer 2   Prompt- und DACH-Semantik              Tasks 09–11
Layer 3   Reader Honesty / Report-Verteidigung   Tasks 12–14
Layer 4   Frontend strict + Confidence UI        Tasks 15–16
Layer 5   Eval + Migration                       Tasks 17–18
Layer 6   Frontend TypeScript                    Tasks 19–21
Layer 7   Graph / Runs / Compare                 Tasks 22–28
Layer 8   Persona Review + UX                    Tasks 29–32
Layer 9   Production Deployment                  Task 33
Layer 10  Security Watchlist                     Task 34
```

**Blocker-Regel:** Kein Layer-Sprung nach oben, wenn ein darunterliegender P0/P1-Task offen ist.

**Ausnahme:** Security-Watchlist darf parallel dokumentiert werden, aber nicht blind mit Dependency-Upgrades erschlagen werden, solange `camel-ai`, `camel-oasis` oder `sentence-transformers` harte Pins setzen. Dependency-Jenga ist bekanntlich der Lieblingssport schlecht gelaunter Build-Systeme.

---

## Teil D — Issue-Mapping

| Issue | Zugeordnete Tasks | Kommentar |
|---|---|---|
| #71 | Tasks 03, 04, 15, 19 | erst schließen, wenn API-Modelle wirklich TS sind und strict parsing läuft |
| #75 | Task 08 + Task 17 | Backend-Score + Tests; UI-Anteil über #76 |
| #76 | Task 16 + Task 22 | UI erst nach Graph-Diff/API und Confidence-Backend |
| #105 | Task 08 + Task 17 | Contradiction-Penalty muss Performance-Budget haben |
| #107 | Task 02 + Task 18 | Schema-Drift fixen reicht nicht; Migration-Skript separat |
| #62 | Task 26 | Runs API zuerst |
| #63 | Task 27 | nach #62 |
| #64 | Task 28 | nach #62/#63 |
| #65 | Task 23 | Compare-Kette Start |
| #66 | Task 24 | nach #65 |
| #67 | Task 25 | nach #66 |
| #69 | Task 29 | vor #70 |
| #70 | Task 30 | nach #69 |
| #74 | Task 22 | Vorbedingung für #76 |
| #106 | Task 33 | separat, nicht an Report-Refactor koppeln |
| #137 | Task 32 | abhängig von Settings/#133 |
| #141 | Task 31 | kleiner UI-Slice, kann nach Frontend-Testbasis laufen |
| #121–#126 | Task 34 | Watchlist, nicht wild Dependencies brechen |

---

## Teil E — Slash-Command-Kompatibilität

### E.1 Vorhandene Commands

| Command | Zweck | Status |
|---|---|---|
| `/agora-next-task` | Orchestrator, liest `PLAN.md`, wählt nächsten Slice, dispatcht Subagent | weiter nutzbar für Tasks 01–17 |
| `/verify-after-subagent` | Pflicht-Verifikation nach Subagent-Run | weiter unverändert nutzen |
| `/fix-task-01-contracts` | Layer 0 Contracts anlegen | weiter nutzbar |
| `/fix-task-02-wire-contracts` | API/Report-Agent verdrahten | weiter nutzbar |
| `/fix-task-03-prompt-semantik` | Prediction-Semantik entfernen | weiter nutzbar |
| `/fix-task-04-anti-dekoration` | dekorative Evidence entfernen | weiter nutzbar |

### E.2 Hinweis zu `/agora-next-task`

Der vorhandene `/agora-next-task` enthält eine feste Heuristik-Tabelle bis Task 17.

Diese `PLAN.md` ist deshalb bewusst so gebaut:

- **Tasks 01–17 bleiben die Slash-Command-kompatible Basis.**
- **Tasks 18–34 sind die neue Open-Issue-Erweiterung.**
- Nach Abschluss von Task 17 sollte die Heuristik-Tabelle im Command erweitert werden.

### E.3 Erweiterung für `/agora-next-task` nach Task 17

Diesen Block später in `.claude/commands/agora-next-task.md` unter „Schritt 2: Task-Auswahl“ ergänzen:

```markdown
| Reihe | Layer | Task | Titel | Aufwand | Subagent | Modell |
|---|---|---|---|---|---|---|
| 16 | 5 | 18 | v1→v2 Report-Migration fertigstellen (#107) | M | agora-refactor-worker | Sonnet |
| 17 | 6 | 19 | Frontend API-Modelle vollständig nach TypeScript migrieren (#71) | M | agora-frontend-worker | Sonnet |
| 18 | 6 | 20 | Composables nach TypeScript migrieren (#72) | L | agora-frontend-worker | Sonnet |
| 19 | 6 | 21 | Kritische Vue-Features nach TypeScript migrieren (#73) | XL | agora-frontend-worker | Sonnet |
| 20 | 7 | 22 | Graph-Diff Modell und API (#74) | L | agora-refactor-worker | Sonnet |
| 21 | 7 | 23 | Vergleichsmodell definieren (#65) | S | agora-doc-worker | Haiku |
| 22 | 7 | 24 | Compare API für Kernmetriken (#66) | L | agora-refactor-worker | Sonnet |
| 23 | 7 | 25 | Compare UI für zwei Branches (#67) | L | agora-frontend-worker | Sonnet |
| 24 | 7 | 26 | Runs API evaluieren und ergänzen (#62) | M | agora-refactor-worker | Sonnet |
| 25 | 7 | 27 | RunsDashboard.vue bauen (#63) | L | agora-frontend-worker | Sonnet |
| 26 | 7 | 28 | Resume/Restart-Aktionen aus UI (#64) | M | agora-refactor-worker | Sonnet |
| 27 | 8 | 29 | Persona Diff gegen Entity-Kontext (#69) | M | agora-frontend-worker | Sonnet |
| 28 | 8 | 30 | Approve / Reject / Regenerate Workflow (#70) | L | agora-frontend-worker | Sonnet |
| 29 | 8 | 31 | Step4 Sticky-Scroll migrieren (#141) | S/M | agora-frontend-worker | Sonnet |
| 30 | 8 | 32 | Graph-Build Batch-Marker-Event (#137) | M | agora-refactor-worker | Sonnet |
| 31 | 9 | 33 | Reverse-Proxy vor Prod-Container (#106) | M | agora-refactor-worker | Sonnet |
| 32 | 10 | 34 | Security-Watchlist konsolidieren (#121–#126) | S | agora-evidence-auditor | Haiku |
```

---

## Teil F — Issue-Drafts / Kommentare

### F.1 Kommentar für #107

```markdown
## Mapping zu PLAN.md

Dieser Issue wird in zwei Slices aufgeteilt:

- Task 02: Runtime-Code auf `schema_version=2` verdrahten
- Task 18: Bestandsdaten-Migration `v1→v2`

Acceptance bleibt:
- idempotentes Skript
- `--dry-run`
- `.v1.bak.json` Backup
- Fixture-Test gegen v1-Report
- Vorher/Nachher-Diff in `docu/`
```

### F.2 Kommentar für #105

```markdown
## Mapping zu PLAN.md

Wird mit Task 08 umgesetzt und über Task 17 evaluiert.

Scope:
- `supports_claim` nicht mehr statisch `true`
- Penalty in `compute_confidence()`
- Performance-Budget: keine 50 LLM-Calls für 50 Claims
- Tests: Pro/Contra-Evidence senkt Confidence sichtbar
```

### F.3 Kommentar für #75

```markdown
## Mapping zu PLAN.md

Backend-Seite:
- Task 08: Score + Penalty + Labeling
- Task 17: Eval-Fixtures + Snapshots

Frontend-Seite:
- Task 16 / #76: Anzeige als Confidence UI
```

### F.4 Kommentar für #76

```markdown
## Mapping zu PLAN.md

Blockiert durch:
- #74 / Task 22 für Graph-Diff Modell/API
- #75 / Task 08 für Confidence Backend
- #105 / Task 08 für Contradiction-Penalty

Umsetzung:
- Task 16: Confidence-Badges, Diff-View, Evidence-Hover
```

### F.5 Kommentar für #71

```markdown
## Mapping zu PLAN.md

Wird nicht als einzelner Big-Bang-Slice umgesetzt.

Reihenfolge:
1. Task 03: JSON-Schema-Dump stabilisieren
2. Task 04: Zod-Spiegel
3. Task 15: Step4 strict-Zod
4. Task 19: `frontend/src/api/*.js` nach `.ts`

Issue erst schließen, wenn Task 19 grün ist.
```

### F.6 Kommentar für #106

```markdown
## Mapping zu PLAN.md

Separater Deployment-Slice: Task 33.

Empfehlung:
- Traefik-Labels oder Sidecar-Nginx
- Backend-Port 5001 nicht mehr öffentlich publishen
- `/api/*` zum Flask/Gunicorn-Service
- Frontend statisch über Proxy ausliefern
- Doku für `tail`-Deployment ergänzen
```

### F.7 Kommentar für #121–#126

```markdown
## Mapping zu PLAN.md

Zusammengefasst in Task 34.

Vorgehen:
- keine wilden Dependency-Upgrades gegen harte Upstream-Pins
- monatlicher `pip-audit` / `uv lock` Check
- schließen erst, wenn blockierende Pins gelöst und Tests grün sind
```

---

## Teil G — Roadmap

| Milestone | Fokus | Tasks | Aufwand solo | Ergebnis |
|---|---|---:|---:|---|
| M1 | Contract Backbone | 01–04 | 1–2 Wochen | Backend/Frontend-Vertrag stabil |
| M2 | Evidence + Confidence | 05–08 | 2 Wochen | Reports belastbarer, #75/#105 Backend |
| M3 | Prompt/DACH + Honesty | 09–14 | 2 Wochen | weniger Marketing-Blabla, bessere Quellenkette |
| M4 | Frontend strict + Eval/Migration | 15–19 | 2–3 Wochen | #71/#107 weitgehend schließbar |
| M5 | TypeScript Migration | 20–21 | 2–4 Wochen | Frontend langfristig wartbarer |
| M6 | Graph/Runs/Compare | 22–28 | 4–6 Wochen | Feature-Backlog EPIC 11/12/15 |
| M7 | Persona Review + UX | 29–32 | 3–5 Wochen | Review-Workflows und bessere Live-UX |
| M8 | Deploy + Security Watch | 33–34 | 1–2 Wochen + laufend | Prod sauberer, CVE-Tracking kontrolliert |

---

## Teil H — Branch- und Commit-Konvention

### Branches

```bash
feat/layer-0-task-01-contracts
feat/layer-5-task-18-report-migration
feat/layer-7-task-26-runs-api
fix/layer-8-task-31-step4-sticky-scroll
chore/layer-10-task-34-security-watchlist
```

### Commit-Muster

```text
feat(contracts): add pydantic report contracts (Task 01, Refs #71 #107)

- add Pydantic v2 report/evidence/persona contracts
- generate JSON schemas
- add contract tests
- keep runtime wiring for Task 02

Tests:
- uv run pytest tests/contracts/ -v
```

### Issue-Schließung

| Situation | GitHub Keyword |
|---|---|
| Issue vollständig erledigt | `Closes #N` |
| Issue nur teilweise bearbeitet | `Refs #N` |
| Issue vorbereitet, aber blockiert | `Refs #N`, Kommentar im Issue |
| Security-Tracker nur geprüft | kein `Closes`, nur Kommentar |

---

## Teil I — Verify-Gates

### Standard nach jedem Subagent

```bash
cd backend && uv run pytest -x -q
cd backend && uv run ruff check .
cd frontend && npm run check && npm run test
```

### Contract-spezifisch

```bash
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/
rg -n '"schema_version": 1' backend/app/ || true
rg -n 'EXPORT_SCHEMA_VERSION = 1' backend/app/ || true
```

### Frontend-spezifisch

```bash
cd frontend
npm run check
npm run test
npm run build
```

### Security-spezifisch

```bash
cd backend
uv run pip-audit || true
uv lock --check
```

---

## Teil J — Sofort-Aktionen

### 1. `PLAN.md` ins Repo legen

```bash
cd /mnt/brain/Projekte/Agora
cp /mnt/data/PLAN_AGORA_OFFENE_ISSUES.md ./PLAN.md
git add PLAN.md
git commit -m "docs(plan): consolidate open issues into slash-command plan"
```

### 2. Bestehende Slash-Commands prüfen

```bash
ls -la .claude/commands/
sed -n '1,160p' .claude/commands/agora-next-task.md
sed -n '1,220p' .claude/commands/verify-after-subagent.md
```

### 3. Nächsten Slice starten

```bash
cd /mnt/brain/Projekte/Agora
claude
> /agora-next-task
```

---

## Teil K — Harte Stopps

- Kein Sammel-PR über mehrere Layer.
- Kein `Closes #N`, wenn der Issue nur vorbereitet wurde.
- Kein Dependency-Upgrade gegen harte Third-Party-Pins ohne Testlauf.
- Kein Frontend-TypeScript-Big-Bang vor stabilen API-Schemas.
- Kein Prod-Deployment-Slice zusammen mit Report-Refactor.
- Kein Auto-Fix-Loop nach rotem Verify. Fehler reporten, Worktree stehen lassen.
