# Agora — Onboarding für Claude Code

## Was ist Agora?

Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.
Stack: **Flask + Pydantic v2 + Vue 3 + Neo4j + Ollama + OASIS** (CAMEL-AI Subprozess).
Status: **v1.0.0 (2026-05-11)** · alle 14 PR-Slices der v1.0-Output-Vertrag-Roadmap aus [`PLAN.md`](PLAN.md) durch · Layer 0–10 grün · Test-Counts: [`docu/STATUS.md`](docu/STATUS.md) · [Release Notes](docu/2026-05-11-v1.0.0-release-notes.md).

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
      report_agent/         Package-Split (Sub-Slice M11.13, #202): agent.py, manager.py, planning.py, evidence.py, prompts.py, schemas.py, sections.py, storage.py, tools.py, workflow.py — Layer-0-Boundary in agent.py + planning.py
      sim/                  M11 Phase 5 Hotspot-Refactor (2026-05-08, 5 PRs): run_state_store, action_log_reader, monitor, interview_client, process_manager extrahiert. `simulation_runner.py` orchestriert nur noch.
      graph/                M11 Phase 5b Hotspot-Refactor (2026-05-08, 3 PRs): graph_dtos, graph_reader, insight_forge_tool extrahiert. `graph_tools.py` orchestriert.
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
| 9 | Production Deployment | grün — M11 Phase 1–4 Hardening (Release-Gating, Static-Analysis-Gates, Multi-Stage `prod`-Image ohne Node/npm/curl + `read_only: true`, Supply Chain) abgeschlossen 2026-05-07. Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, `?token=`-Block in Prod ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke auf `main`/Tags/`workflow_dispatch` ✅ (`docker-image.yml::prod-proxy-smoke`). PR-Trigger seit 2026-05-06 wegen ~30 min Laufzeit pausiert und vor Release neu zu bewerten. |
| 10 | Security Watchlist (CVE-Tracking, pip-audit) | grün — CVE-Monitor wöchentlich (`.github/workflows/cve-monitor.yml`, `pip-audit --strict` ohne `--ignore-vuln`), Hardstop 2026-07-30 verdrahtet (Workflow failt ab dann), Risk-Register mit Eskalationspfad (`docu/dependency-risk-register.md`). Issues #121–#126 bleiben open bis Upstream patcht. Zusätzlich CVE-Tracker #296/#297/#298 seit 2026-05-07 unter Beobachtung. Phase 4 Supply Chain (`dependency-review.yml`, `codeql.yml`, GHCR Build-Provenance-Attestation, SPDX-JSON-SBOM-Artefakt) zusätzlich aktiv. |

## Aktive Hot-Spots / offene Hauspflicht

Layer-0–6 + 9–10 sind durch. **v1.0-Output-Vertrag-Pfad** (PLAN.md): Phase 1 + P2.1/P2.2/P3.1/P3.3/P3.4/P4.2 stehen, **offen sind P3.2-Verdrahtung, P4.1 (Report-Modi), P4.3 (ZIP-Bundle), P4.4 (E2E-Smokes)**. P2.3 läuft separat im Worktree `feat/m11-7c-report-hypotheses`. Daneben aktuelle M11-Baustellen:

- **Coverage-Gate-Anhebung** (M11.2/M11.3): Aktuelle Schwellen Backend 53 % / Frontend 24 %. Ziel Backend 70 % / Frontend 60 % schrittweise. Coverage-Reports als Artifacts `backend-coverage` / `frontend-coverage` (14 Tage Retention) in `ci.yml`.
- **Phase 6 Contract-Generation + Status-Sync:** Contract-Dump reproduzierbar machen, Frontend-Zod-Spiegel automatisiert gegen Pydantic prüfen, `scripts/sync-status.sh` als CI-Pflichtschritt.
- **Phase 7 / M11.4 Playwright-Smokes:** Drei stabile E2E-Smokes — Health/Login, Upload+Graph, Minimalreport. Keine 90-Test-Pyramide.
- **M11.5 Komplexitäts-Gate:** `radon` Backend, ESLint/size-limit Frontend.
- **M11.6 API-Envelope:** Error-/Success-Envelopes vollständig durchziehen.
- **Frontend-Hotspots (Issue #203):** `Step2EnvSetup.vue` 667 LOC (war 1804, -63 %), `Step4Report.vue` 797 LOC (war 1287, -38 %) — bereits durch Phase-5/5b-analoge Schnitte reduziert, unter Schwelle. Issue #203 zum Schließen vorbereiten (separater Slice).
- **gevent ↔ OASIS-Subprozess Smoke:** `subprocess.Popen` läuft bei aktivem `gevent.monkey.patch_all()` standardmäßig durch den Patch — bei jedem Slice, der den OASIS-Pfad anfasst, per `scripts/verify-deploy.sh` smoken.
- **Init-Logs doppelt:** Folge-Slice braucht Fork-Safety-Verifikation der Neo4j/Redis-Pools vor `--preload`-Aktivierung.
- **Dependabot-Aufräumen:** Offene PRs #323 (`mistune` 3.1.4 → 3.2.1), #326 (`pygments` 2.19.2 → 2.20.0). PR #315 (`camel-ai`) bleibt blockiert durch `camel-oasis==0.2.5` hard pin.
- **Live-Settings #212 (P2):** Erst nach M11-Stabilisierung.

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

## Erwartete Tool-Nutzung (proaktiv)

- **code-review-graph** — Pflicht-First-Stop bei Code-Exploration, *bevor* `rg`/`grep`/`Read`/`Glob`. Tree-sitter-basierter persistenter Knowledge-Graph mit strukturellem Kontext (Caller, Dependents, Test-Coverage). Tool-Routing:

  | Frage | Graph-Tool | Statt |
  |---|---|---|
  | Code-Review eines Diff | `detect_changes` + `get_review_context` | komplette Files via `Read` |
  | Blast-Radius einer Änderung | `get_impact_radius` | manuelles Import-Tracing |
  | Welche Flows sind betroffen? | `get_affected_flows` | `rg` durch alle Service-Files |
  | Wer ruft `<symbol>` auf? | `query_graph` mit `pattern=callers_of` | `rg "<symbol>"` |
  | Caller/Callee/Tests für `<symbol>` | `query_graph` mit `pattern=callees_of` / `tests_for` | `rg` |
  | Funktion/Klasse finden | `semantic_search_nodes` | `rg "def <name>"` |
  | Architektur-Überblick | `get_architecture_overview` + `list_communities` | mehrere `Read` über `__init__.py` |
  | Refactor-Hot-Spots | `find_large_functions_tool` + `get_hub_nodes_tool` | manuelle `git grep` |
  | Refactor-Planung (Renames, Dead-Code) | `refactor_tool` | manuelle Cross-Repo-Suche |

  **Fallback auf `rg`/`grep`/`Read`** nur wenn der Graph die Frage nicht abdeckt: Bash-Skripte, GitHub-Workflow-yml, Markdown, Config-Files, generierte Schemas. Der Graph parst Code-Symbole — bei Nicht-Code-Files ist Direkt-Lesen korrekt.

  Workflow: Graph aktualisiert sich automatisch via Hooks. Bei Code-Review zuerst `detect_changes` für Risk-Score. Vor Refactor `get_minimal_context_tool` (token-spart gegenüber `Read` ganzer Files). Vor Slice-Cuts in verbleibenden Hot-Spots `get_hub_nodes_tool` für Schnitt-Grenzen. F8 Frontend-Hotspots sind bereits unter Schwelle (667 LOC / 797 LOC).

- **context7** — bei jeder Task, die Bibliotheken/Frameworks/SDKs/CLIs/Cloud-Services berührt (Flask, Pydantic v2, Vue 3, Vite, Pinia, Neo4j-Driver, OASIS/CAMEL, Ollama, OpenAI-kompatible Chat-/Tool-Call-APIs, pytest, uv, …): aktuelle Docs prüfen, **bevor** Code geschrieben wird.

- **GitHub-Suche / `gh`** — Debugging von Third-Party-Verhalten (OASIS-Eigenheiten, Neo4j-Vector-Search-Kanten, Ollama-Tool-Call-Payloads, Qwen/GPT-OSS-Reasoning-Blöcke, CAMEL-Memory-/Context-Edge-Cases) zuerst gegen Upstream-Issues/PRs spiegeln.

- **sequential-thinking** — automatisch für Multi-File-Refactors, pipelinespannende Änderungen (graph → env → simulation → report), Debugging über die Flask↔OASIS-Subprozess-Grenze, oder Tasks mit unklarem Lösungspfad.

Defaults, keine Eskalation. Wenn du eins davon überspringst, notiere kurz warum.

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
- **Neue OASIS/CAMEL-Runner-Skripte ohne `apply_camel_context_floor()` + `enforce_memory_token_limit()`-Aufruf nach `generate_*_agent_graph(...)`.** Sonst kappt CAMELs `ScoreBasedContextCreator` jeden Agent-Memory bei 8192 Tokens — unabhängig vom realen Modell-Context. Floor wird zentral in `backend/scripts/_sim_common.py::apply_camel_context_floor()` gepflegt; Pro-Modell-Heuristik in `backend/scripts/agent_tools.py::_heuristic_context_limit()`. User-Override via `LLM_CONTEXT_LIMIT` und `LLM_MODEL_CONTEXT_LIMITS_JSON` (Vorrang vor Heuristik)
- Hartkodierte `token_limit`-Defaults in CAMEL-/OASIS-Anbindungen (8192, 4096, 16384) — immer aus `_resolve_memory_token_limit(model_name)` lesen, damit Frontend-gewählte Cloud-Modelle (Gemini 3 ≈ 1 M, Qwen3-Coder 256 k, GPT-OSS 128 k) ihren echten Context-Window nutzen können
- **Evidence-Gating-Pflicht-Anker (ADR-0002) entfernen oder schwächen.** Fünf Anker sind hart verankert in [`docu/decisions/0002-evidence-gating.md`](docu/decisions/0002-evidence-gating.md): (1) `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts.py`, (2) Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`, (3) Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`, (4) Validator `cross_stakeholder_for_high`, (5) Validator `reject_inferred_in_high_confidence`. Schwächungen wie „cross_stakeholder von 2 auf 1 Gruppe absenken", „Hedge-Liste verkürzen", „inferred aus Enum entfernen" oder „priority=hard durch soft-hint ersetzen" verlangen einen Supersedes-ADR (`0002-supersedes.md`) mit User-Sign-off, kein stilles Refactor.
