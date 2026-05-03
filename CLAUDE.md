# Agora — Onboarding für Claude Code

## Was ist Agora?

Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.
Stack: **Flask + Pydantic v2 + Vue 3 + Neo4j + Ollama + OASIS** (CAMEL-AI Subprozess).
Status: v0.9.0+, Backend 1289 Tests, Frontend 141 Tests, Pydantic-Contract-Architektur abgeschlossen (Layer 0–6 grün, Layer 7–10 in Arbeit).

## Sofort wichtig

- **Branch-Hygiene:** Nie auf `main` direkt pushen. Branch-Namen: `feat/task-XX-kurztitel`. Linear-FF-Merge auf main, keine Rewrites publizierter Commits.
- **Tests sind die Spec.** Pflichttests vor Refactor lesen. TDD: erst RED, dann GREEN, dann Commit.
- **Pakete unter Linux:** `nala` statt `apt`. Python-Deps via `uv`.
- **Layer-Reihenfolge ist verbindlich** (siehe unten).
- **Keine US-Cloud-Lock-ins.** Ollama-kompatibel als Fallback bleibt Pflicht.

## PR-Workflow (Pflicht)

Nach jedem `gh pr create`:

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

**Gemini-Code-Assist** reviewed automatisch innerhalb ~60–120 s. Findings
sind nach `priority` markiert (HIGH / MEDIUM / LOW). Workflow:

1. **HIGH:** immer adressieren, bevor mergen — entweder direkt im
   gleichen Branch nachpatchen oder als Followup-Sub-Slice
   (`fix(scope): Gemini-Followup auf <PR#>`).
2. **MEDIUM:** je nach Scope. i18n-Misses, Exception-Specifity,
   stable-keys → meistens fixen. Style-Geschmack → explizit ablehnen
   im Arbeitsprotokoll, nicht stillschweigend ignorieren.
3. **LOW:** kann oft als „Out of Scope" gemerged werden, mit Verweis im
   Arbeitsprotokoll.

Erst nach Findings-Sichtung mergen — `git checkout main && git merge --ff-only <branch> && git push origin main`.

## Stack-Map

```
backend/                    Python 3.11, uv, Flask, Pydantic v2, pytest
  app/
    contracts/              Layer 0: Single Source of Truth (Pydantic v2)
    api/                    HTTP-Routen (Flask Blueprints)
    services/               Business-Logik
      report_agent.py       Sub-Slice 02a/02b/02c: schema_version=2, EvidenceMapModel-Validation
      evidence_binder.py    Sub-Slice 07: Contradiction-Penalty, kein dekoratives Fallback
      confidence_calculator.py  Sub-Slice 08: Match-Score-Cap + Verified-Quellen-Gate
      oasis_profile_generator.py  voice_register-Pflichtfeld (Sub-Slice 10)
      prepare_service.py    Sub-Slice 20a/b/22: PersonaQuotaPlan-Pipeline komplett
      simulation_runner.py  Sub-Slice 21: OASIS_DB_PATH pro Sim
    models/                 Dataclasses (werden migriert)
    storage/                Neo4j-Adapter
    utils/llm_client.py     Sub-Slice 05: chat_json strict-Schema-Mode
  tests/
    contracts/              Pflicht für jeden Vertrag
    api/                    Schema-Tests, jsonschema-basiert
    services/
    eval/                   Sub-Slice 17: Baseline-Eval-Suite + Snapshots
  scripts/                  OASIS-Subprozess + run_*_simulation.py
frontend/                   Vue 3 + JS + Pinia + Vitest + Zod
  src/
    contracts/              Zod-Spiegel zu backend/app/contracts/
      personaQuotaContract.ts  Sub-Slice 20c/24
      reportContract.ts        Sub-Slice 02b
    components/
      Step2EnvSetup.vue     Quoten-Editor (Sub-Slice 20c/24)
      Step4Report.vue       Sub-Slice 15: strict-Zod-Parse + Schema-Banner
schemas/                    auto-generiert via app.contracts.dump_schemas
docu/                       Architektur, Logs, Plans, Arbeitsprotokolle
prompts/                    UI-Prompt-Vorlagen
```

## Architektur-Layer (Status)

Änderungen nur **layer-aufwärts**. Layer 1 ohne Layer 0 ist verboten.

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel + JSON-Schema-Dump | grün (Sub-Slice 02a–c) |
| 1 | Backend-Hardening (Quoten, Evidence-Dedup, Confidence) | grün (06–08, 20a/b/22, 32) |
| 2 | DACH-Voice + Prompt-Semantik (`future prediction` weg) | grün (09, 11, Wording-Glossar v1) |
| 3 | Reader-Honesty (Quotes, Time-Series, Section-Dedup) | grün (12–14) |
| 4 | Frontend (Zod-strikt, Diff/Confidence-UI, Quoten) | grün (15, 16a/b, 20c/24) |
| 5 | Eval/Baseline (Fixtures, Snapshot-Tests) + v1→v2-Migration | grün (17, 25) |
| 6 | Frontend-TypeScript-Migration (API, Composables, Pinia) | grün (26, 27, 28 — #71/#72/#73) |
| 7 | Graph / Runs / Compare | teilweise — done: 29 (#65), 33 (#62), 35 (#64). Offen: 22 #74 (Graph-Diff), 24 #66 (Compare-API), 25 #67 (Compare-UI), 27 #63 (RunsDashboard) |
| 8 | Persona Review + UX | teilweise — done: 30 (#141 Sticky-Scroll). Offen: 29 #69 (Persona-Diff), 30 #70 (Approve/Reject/Regenerate), 32 #137 (Graph-Build-Batch-Marker) |
| 9 | Production Deployment (Reverse-Proxy, gevent, SSE-Auth-Frontend) | offen — Task 33 (#106). Sub-Slice 19 (gunicorn-Sync) als Workaround vorhanden |
| 10 | Security Watchlist (CVE-Tracking, pip-audit) | grün dokumentiert (Sub-Slice 31, Refs #121–#126) — Upstream-Pins blockieren weitere Closes |

## Aktive Hot-Spots / offene Hauspflicht

Die ursprünglichen Layer-0–6-Hot-Spots aus dem ChatGPT-Audit sind alle
gefixt. Aktuelle bekannte Baustellen (Layer 7–9):

- **gunicorn-Worker-Modell** — sync mit `--timeout 600` (Sub-Slice 19) ist
  Workaround. Saubere Lösung: `-k gevent` (Plan: [`docu/2026-04-29-prod-slice2-gunicorn.md`](docu/2026-04-29-prod-slice2-gunicorn.md)).
  Caveat: gevent-Monkey-Patching ↔ OASIS-Subprozess-Entkopplung muss
  per Smoke verifiziert werden.
- **SSE-Auth** — Frontend nutzt noch `?token=`-URL-Fallback statt
  signed-tickets via [`POST /api/auth/ticket`](backend/app/api/auth.py).
  Backend-Pfad existiert; Frontend-Migration steht aus.
- **Reverse-Proxy vor Prod-Container** — offen [#106](https://github.com/arn0ld87/Agora/issues/106).
- **Init-Logs doppelt** — gunicorn ohne `--preload`. Kein Bug, aber
  unschön. Folge-Slice braucht Fork-Safety-Verifikation der
  Neo4j/Redis-Pools vor `--preload`-Aktivierung.

## Kommandos (immer diese)

```bash
# Backend
cd backend && uv sync --group dev
cd backend && uv run pytest -x -q
cd backend && uv run pytest tests/contracts/ -v          # Contract-Tests
cd backend && uv run python -m app.contracts.dump_schemas # Schemas regenerieren
cd backend && uv run ruff check . && uv run mypy app

# Frontend
cd frontend && npm ci
cd frontend && npm run check        # lint + test + build (alles)
cd frontend && npm test -- --run    # nur tests
cd frontend && npm run lint
cd frontend && npm run build

# Container (Prod-Stack lokal)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker exec agora curl -fsS http://localhost:5001/health

# CI lokal simulieren
git diff --exit-code schemas/    # nach dump_schemas darf nichts driften
```

## Verifikations-Disziplin

Bevor du Variablen umbenennst oder Pfade anlegst, **immer erst** `rg`-prüfen:

```bash
rg -n "<symbol>" backend/
find . -path "*<pattern>*"
```

ChatGPT/Claude-LLM-Vorschläge sind oft präzise, aber Variablen-Namen
sind manchmal halluziniert. Verifiziere **immer**.

## Subagent-Routing (Max-Plan)

Optimierungsziel ist **Rework-Vermeidung**, nicht Token-Sparen. Layer-0-Drift
oder Wording-Glossar-Verstöße kosten in der Re-Review mehr als ein direkter
Opus-Run gespart hätte.

Ziel-Mix: ~35 % Opus, ~55 % Sonnet, ~10 % Haiku.

| Aufgabe | Modell | Subagent | Anteil-Ziel |
|---|---|---|---|
| Architektur-Entscheidung, Cross-Layer-Refactor, ambige Specs | Opus | (Lead, kein Subagent) | ~25 % |
| Code-Review kritischer Pfade (contracts, evidence_binder, report_agent) | Opus | `feature-dev:code-reviewer` | ~10 % |
| Refactor 2+ Dateien, Pydantic-Migration | Sonnet | `agora-refactor-worker` | ~25 % |
| Pydantic-Tests, FSM-Übergänge, Persona-Quoten | Sonnet | `agora-test-worker` | ~15 % |
| Vue/Pinia/Zod-Spiegel | Sonnet | `agora-frontend-worker` | ~10 % |
| Read-only Audit (Evidence, Wording-Glossar) | Sonnet | `agora-evidence-auditor` | ~5 % |
| Dokumentation, CHANGELOG, Arbeitsprotokolle | Haiku | `agora-doc-worker` | ~10 % |

### Opus-Trigger (überstimmen das Default-Routing)

Auch wenn ein Sonnet-Subagent für die Aufgabe definiert ist — bei diesen
Signalen direkt Opus ziehen:

- Layer-0 (Pydantic-Contracts) wird angefasst
- Mehrere Layer gleichzeitig betroffen
- Wording-/Prompt-Semantik (Layer 2, Glossar v1)
- Spec ist ambig oder Tests fehlen noch
- Pre-PR-Self-Review **vor** `gh pr create` (fängt Drift bevor Gemini sie sieht)

## Slash-Commands (im Repo, Cloud-portabel)

`.claude/commands/`:

- `/agora-next-task` — Master-Orchestrator: pickt nächsten offenen
  Sub-Slice aus PLAN.md, dispatched passenden Subagent, verifiziert,
  committet, pusht.
- `/verify-after-subagent` — Pflicht-Verifikation nach jedem
  Subagent-Run (sequential gate).
- `/fix-task-01..04-*` — Templates aus dem Layer-0–4-Refactor
  (inhaltlich abgearbeitet; können archiviert werden).

## Verboten

- Dataclasses für API-Verträge → Pydantic v2 (`extra="forbid"`)
- Inline-JSON-Schemas → immer aus Pydantic ableiten via `model_json_schema()`
- `apt` (nutze `nala`)
- US-Marketing-Phrasen in Reports („revolutionary", „seamless", „prediction of the future")
- Wording-Glossar v1 verletzen (siehe [`docu/glossary-wording.md`](docu/glossary-wording.md), Issue #175): `prediction`, `rehearsal`, `god's eye view`, `high-fidelity digital world`, `public opinion prediction`, `Agentic-Prediction-Engine` → durch Glossar-Equivalente ersetzen
- `print()` in Prod-Code → strukturiertes Logging via `app.logger`
- Schema-Strings inline kopieren → über Re-Export aus `app.contracts`
- `git push --no-verify` ohne explizite User-Freigabe
- Auf `main` mergen ohne Gemini-Findings-Sichtung (siehe PR-Workflow oben)
- Hartkodierte UI-Strings in `Step*.vue` — immer `vue-i18n` (`t(...)`) + Keys in `de.json`+`en.json`
