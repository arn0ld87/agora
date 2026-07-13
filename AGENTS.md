# AGENTS.md

Guidance für Codex, Claude Code und andere Agent-Runtimes in diesem Repository.

Diese Datei ist bewusst schlank. Detail-Runbooks unter [`docs/runbooks/`](docs/runbooks/).
Test-Counts und Versionsstände in [`docs/STATUS.md`](docs/STATUS.md), operativer Slice-Plan in [`PLAN.md`](PLAN.md).

## Projekt

Agora ist ein **lokal-first** Multi-Agent-Simulator für DACH-Zielgruppenreaktionen. Pipeline:
Dokument hochladen → Wissensgraph extrahieren → Personas spawnen → OASIS-Simulation → DACH-Report.

**Stack:** Flask (Python 3.14) + Pydantic v2 + Vue 3 + Vite + Pinia + Neo4j 5.18 CE + OASIS (`camel-oasis`)
+ Redis + Ollama. Package-Manager: `uv` (Backend), `npm` (Frontend).
**Single-User**, lokal oder hybrid, **kein öffentliches SaaS** ([ADR-0001](./docs/decisions/0001-auth-model.md)).

**Status:** v1.0.0 (Release 2026-05-11). Layer 0–6 grün, 7–8 teilweise, 9–10 grün. M11 Phase 1–5b durch.
Aktive Welle: **Onboarding & Provider-Unification** (Phase 1 Slices 1–4.3.4 gemerged, Phase 2 Slice 5 läuft —
Sub-Slice 5.0/5.1 gemerged, 5.2 in Arbeit). Roadmap: [`PLAN.md`](PLAN.md).
Layer-Detail: [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md).

## Sofort wichtig

- **Tool-Pipeline (harmonisiert mit context-mode):** `code-review-graph` → `context7` →
  `ctx_batch_execute` → `ctx_execute` → **erst dann** `Read`/`Bash`. Detail:
  [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md).
- **context-mode ist die Execution-Layer.** PreToolUse-Hooks limitieren Bash (nur git/fs/nav,
  kein curl/wget), Read (nur zum Editieren, Analysen via ctx_execute_file), WebFetch
  (erlaubt, aber ctx_fetch_and_index für Research bevorzugt).
- **Pre-Push-Gate ist Pflicht.** Vor jedem Push `bash scripts/pre-push-gate.sh` (Sub-Scopes
  `backend|frontend|schemas` erlaubt). CI und lokal laufen denselben Gate-Satz — kein
  `--no-verify`-Bypass. Runbook: [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md).
- **Branch-Hygiene:** Nie direkt auf `main` pushen. PR-Workflow inklusive Gemini-Sichtung:
  [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md).
- **Worktree für Slices:** `/private/tmp/agora-<slice-id>/`. Details:
  [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).
- **Layer-Reihenfolge ist verbindlich.** Layer 1 ohne Layer 0 ist verboten.
- **Tests sind die Spec.** TDD: erst RED, dann GREEN, dann Commit.
- **Pakete unter Linux:** `nala` statt `apt`. Python-Deps via `uv`.
- **Keine US-Cloud-Lock-ins.** Ollama- oder OpenAI-kompatible Fallbacks bleiben Pflicht.

## Stack-Map (Kurzfassung)

```
backend/                        Python 3.14, uv, Flask, Pydantic v2, pytest
  app/
    contracts/                  Layer 0: Single Source of Truth (Pydantic v2, extra="forbid")
    api/                        HTTP-Routen (Flask Blueprints)
    services/
      report_agent/             Layer 7: Report-Pipeline
      evidence_binder/          Evidence-Gating (ADR-0002)
      embedding_migration.py    Lifecycle pending→running→validating→completed (ADR-0007)
      embedding_reembedder.py   Echte Neo4j-Re-Embedding-Engine (Onboarding 4.3.4 + 4.4 Fact-Phase)
      embedding_service.py      Konfigurations-Service (Onboarding 4.2)
      embedding_ollama_pull.py  Ollama-Modell-Download (Onboarding 4.3.1)
    llm/
      providers/registry.py     Provider-Detection-SSoT (detect_provider mode="http"|"oasis")
    storage/                    Neo4j-Adapter, Embeddings, NER, Search
    utils/                      llm_client, auth, json_io
  tests/{contracts,api,services,eval}
  scripts/                      OASIS-Subprozess-Runner

frontend/                       Vue 3 + TS + Pinia + Vitest + Zod
  src/
    contracts/                  Zod-Spiegel zu backend/app/contracts/
    api/                        index, graph, simulation, report, runs, stream
    composables/                useEventStream, usePolling, useWorkspaceMode, …
    components/Step*.vue        Pipeline-Steps
    components/AiModelPicker.vue  Unified Model Picker (ADR-0009, Onboarding 5.1)
    layouts/                    Workspace-Shell

schemas/                        auto-generiert via `python -m app.contracts.dump_schemas`
deploy/                         nginx-Sidecar, prod-with-proxy compose
docs/                           Lebende Dokumentation und Runbooks
design/v3-source/               Vendoriertes Design v4 (App-Shell)
```

Detail: [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md).

## Commands

```bash
# Setup
npm run setup:all                # root + frontend + backend uv sync

# Dev
npm run dev                      # backend + frontend parallel
npm run backend                  # Flask :5001
npm run frontend                 # Vite :5173

# Quality-Gate
npm run check                    # lint + test + build (alles)
bash scripts/pre-push-gate.sh    # CI-mirror: vor jedem Push Pflicht

# Backend
cd backend && uv run pytest -x -q
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run python -m app.contracts.dump_schemas
cd backend && uv run ruff check . && uv run mypy app

# Frontend
cd frontend && npm run check
cd frontend && npm test -- --run

# Prod-Stack lokal (inkl. Proxy)
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz

# Schema-Drift-Check (CI lokal)
git diff --exit-code schemas/
```

## Konfiguration (Essentials)

Alles über `.env` am Repo-Root, geladen von `backend/app/config.py`. Im Non-Debug Pflicht:
`LLM_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, `SECRET_KEY`, `AGORA_AUTH_TOKEN`.

Wichtige nicht-offensichtliche Knöpfe:

- **`EMBEDDING_MODEL` und `VECTOR_DIM` müssen zusammenpassen** — Tabelle in
  [`docs/provider-runtime-settings.md`](docs/provider-runtime-settings.md).
- `OLLAMA_THINKING=false` — strippt Reasoning-Blöcke bei Qwen3/GPT-OSS/DeepSeek-R1.
  Wirkt sowohl in den OASIS-Subprozess-Skripten als auch im
  Flask-`LLMClient.__init__` (Sub-Slice 05.2) — überstimmt
  `reasoning_effort`-Default.
- `LLM_DISABLE_JSON_MODE=true` — deaktiviert `response_format=json_object`.
- `LLM_CONTEXT_LIMIT` / `LLM_MODEL_CONTEXT_LIMITS_JSON` — überschreiben die Pro-Modell-Heuristik.
  Heuristik ist seit Sub-Slice 05.5 doppelt verdrahtet: CAMEL
  `ScoreBasedContextCreator`-Floor in den OASIS-Subprozessen UND
  `LLMClient._num_ctx`-Resolver (`_resolve_num_ctx` in
  `app/utils/llm_client.py`). Ohne Override greift die Modell-Familie-Tabelle
  (z. B. `gemini-3 = 1M`, `qwen3-coder = 256k`, `gpt-oss = 128k`,
  `nemotron = 128k`); Legacy-Default `OLLAMA_NUM_CTX = 8192` greift nur noch
  bei unbekannten Modellen.
- `PERSONA_REVIEW_ENABLED`, `ENABLE_AGENT_TOOLS`, `ENABLE_WEB_TOOLS` — opt-in Features.
- `EVENT_BUS_BACKEND=auto|redis|file` — IPC-Adapter-Wahl.

Vollständige Liste mit Kommentaren: [`docs/provider-runtime-settings.md`](docs/provider-runtime-settings.md)
und [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md).

## Verboten

- Dataclasses für API-Verträge — Pydantic v2 (`extra="forbid"`)
- Inline-JSON-Schemas — immer aus Pydantic via `model_json_schema()`
- `apt` — `nala` nutzen
- US-Marketing-Phrasen in Reports (»revolutionary«, »seamless«, »prediction of the future«)
- Wording-Glossar v1 verletzen — [`docs/glossary.md`](docs/glossary.md)
- `print()` in Prod-Code — strukturiertes Logging via `app.logger`
- Schema-Strings inline kopieren — über Re-Export aus `app.contracts`
- `git push --no-verify` ohne explizite User-Freigabe
- Auf `main` mergen ohne Gemini-Findings-Sichtung
- Hartkodierte UI-Strings in `Step*.vue` — immer `vue-i18n` (`t(...)`) + Keys in `de.json`/`en.json`
- Hartkodierte `token_limit`-Defaults in CAMEL/OASIS — immer aus `_resolve_memory_token_limit(model_name)`
- Neue Query-Tokens (`?token=`) in URLs — signed tickets (`?ticket=`) sind der einzige URL-bound Auth-Pfad
- Neue „temporäre" CVE-Ignores ohne Issue, Owner, Deadline und Hardstop-Datum
- Lokale Provider-Detection-Heuristiken — `backend/app/llm/providers/registry.py::detect_provider` ist SSoT
  (Phase F, #669/#670/#671 delegieren bestehende Stellen dorthin)

## Aktive Epics (Stand 2026-07-13)

- **Onboarding & Provider-Unification** (laufende Welle):
  - **Phase 1 (gemerged):** Slices 1–4.3.4 — kanonische Provider-/Modell-/Embedding-Verträge,
    User-Profile + resumierbares Onboarding-Grundgerüst, Provider-Discovery, Embedding-Configuration-
    Service, Embedding-Migration-Lifecycle, Frontend-Store/View, **echte Neo4j-Re-Embedding-Engine
    mit Resume-Cursor**, zentrales `pre-push-gate.sh`, F401-Cleanup. PRs #683 → #694.
  - **Phase 2 (Slice 5, läuft):** Unified Model Picker (Sub-Slice 5.0 Sub-Plan + ADR-0009 gemerged,
    5.1 `AiModelPicker.vue` mit reka-ui gemerged, 5.2 in Arbeit). Branch: `codex/onboarding-model-picker`.
  - Detail: [`docs/epics/onboarding-provider-unification/`](docs/epics/onboarding-provider-unification/).
- **Design Language v4 — App-Shell-Port:** Slices A–E durch, **F + G1 (Settings General/Integrations)
  + G2 (API Keys real) gemerged**. Branch `feat/design-v4-epic`. Vendoriert in [`design/v3-source/`](design/v3-source/).
- **v1.0-Output-Vertrag** ([`PLAN.md`](PLAN.md)) — offen: P3.2, P4.1, P4.3, P4.4.
- **Observability** ([`docs/plans/active/`](docs/plans/active/)):
  - Slice 1 — End-to-End-Tracing ✅ (PR #468)
  - Slice 2 — Metrics ✅ (PR #473)
  - Slice 3 — Logs-Correlation ✅ (PR #474)
  - Slice 4 — SLOs/Alerts offen
- **Phase F — Provider-Detection-Delegation** (TDD, je eigener PR): #669
  (`simulation_lifecycle._detect_default_provider`), #670 (`_sim_common._is_ollama_route` think/num_ctx),
  #671 (`embedding_service._detect_provider` vereinheitlichen).
- **Dependency-Hardstops** ([`docs/dependency-risk-register.md`](docs/dependency-risk-register.md)):
  `nltk` PYSEC-2026-597 + GHSA-p4gq-832x-fm9v → **2026-07-30**; Trivy OS-Layer CVE-2026-24049/23949 → **2026-08-30**.

## Wichtige ADRs (kurz)

| ADR | Thema | Status |
|---|---|---|
| [0001](./docs/decisions/0001-auth-model.md) | Auth-Modell (Single-User) | Accepted |
| [0002](./docs/decisions/0002-evidence-gating.md) | Evidence-Gating (5 Hartanker) | Accepted — nicht schwächen |
| [0003](./docs/decisions/0003-pydantic-settings-migration.md) | Pydantic-Settings-Migration | Accepted |
| [0004](./docs/decisions/0004-cve-upstream-escalation.md) | CVE-Upstream-Escalation | Accepted |
| [0006](./docs/decisions/0006-ai-provider-connections.md) | AI-Provider-Connections | Accepted (Onboarding 3) |
| [0007](./docs/decisions/0007-embedding-configuration-and-index-migration.md) | Embedding-Config + Index-Migration | Accepted (Onboarding 4) |
| [0008](./docs/decisions/0008-single-user-profile-and-onboarding.md) | Single-User-Profile + Onboarding | Accepted (Onboarding 2) |
| [0009](./docs/decisions/0009-unified-model-picker.md) | Unified Model Picker | Accepted (Onboarding 5.0) |

## Referenz

- [`docs/`](docs/) — Doku-Index (Architektur, Deployment, Security, Operations)
- [`docs/runbooks/`](docs/runbooks/) — Detail-Runbooks (Tool-Pflicht, PR-Workflow, Worktree, Subagent-Routing, Pre-Push-Gate, Layer)
- [`docs/STATUS.md`](docs/STATUS.md) — Test-Counts, Coverage, Milestones
- [`docs/epics/onboarding-provider-unification/`](docs/epics/onboarding-provider-unification/) — laufende Welle
- [`docs/plans/active/`](docs/plans/active/) — abgenommene Pläne (Observability, …)
- [`PLAN.md`](PLAN.md) — Operativer Slice-Plan
- [`CHANGELOG.md`](CHANGELOG.md) — Release-Notes
- [`CLAUDE.md`](CLAUDE.md) — Claude-spezifische Eigenheiten (Subagent-Routing, Pre-Commit-Gate, Runbooks)

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
