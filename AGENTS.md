# AGENTS.md

Guidance für Codex, Claude Code und andere Agent-Runtimes in diesem Repository.

Diese Datei ist bewusst schlank. Detail-Runbooks unter [`docs/runbooks/`](docs/runbooks/).
Test-Counts und Versionsstände in [`docs/STATUS.md`](docs/STATUS.md), operativer Slice-Plan in [`PLAN.md`](PLAN.md).

## Projekt

Agora ist ein **lokal-first** Multi-Agent-Simulator für DACH-Zielgruppenreaktionen. Pipeline:
Dokument hochladen → Wissensgraph extrahieren → Personas spawnen → OASIS-Simulation → DACH-Report.

**Stack:** Flask (Python 3.12) + Pydantic v2 + Vue 3 + Vite + Pinia + Neo4j 5.18 CE + OASIS (`camel-oasis`)
+ Redis + Ollama. Package-Manager: `uv` (Backend), `npm` (Frontend).

**Status:** v1.0.0 (2026-05-11). Layer 0–6 grün, 7–8 teilweise, 9–10 grün. M11 Phase 1–5b durch.
Aktuelle Roadmap: [`PLAN.md`](PLAN.md). Layer-Detail: [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md).

## Sofort wichtig

- **Tool-Pipeline (harmonisiert mit context-mode):** `code-review-graph` → `context7` →
  `ctx_batch_execute` → `ctx_execute` → **erst dann** `Read`/`Bash`. Detail:
  [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md).
- **context-mode ist die Execution-Layer.** PreToolUse-Hooks limitieren Bash (nur git/fs/nav,
  kein curl/wget), Read (nur zum Editieren, Analysen via ctx_execute_file), WebFetch
  (erlaubt, aber ctx_fetch_and_index für Research bevorzugt).
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
backend/                    Python 3.12, uv, Flask, Pydantic v2, pytest
  app/
    contracts/              Layer 0: Single Source of Truth (Pydantic v2, extra="forbid")
    api/                    HTTP-Routen (Flask Blueprints)
    services/               Business-Logik (report_agent/, evidence_binder, …)
    storage/                Neo4j-Adapter, Embeddings, NER, Search
    utils/                  llm_client, auth, json_io
  tests/{contracts,api,services,eval}
  scripts/                  OASIS-Subprozess-Runner

frontend/                   Vue 3 + TS + Pinia + Vitest + Zod
  src/
    contracts/              Zod-Spiegel zu backend/app/contracts/
    api/                    index, graph, simulation, report, runs, stream
    composables/            useEventStream, usePolling, useWorkspaceMode, …
    components/Step*.vue    Pipeline-Steps
    layouts/                Workspace-Shell

schemas/                    auto-generiert via `python -m app.contracts.dump_schemas`
deploy/                     nginx-Sidecar, prod-with-proxy compose
docs/                       Lebende Dokumentation und Runbooks
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

## Aktive Epics

- **Design Language v4 — App-Shell-Port:** Integration-Branch `feat/design-v4-epic`, Slices A–E durch,
  F läuft. Vendoriert in [`design/v3-source/`](design/v3-source/).
- **v1.0-Output-Vertrag** ([`PLAN.md`](PLAN.md)) — offen: P3.2, P4.1, P4.3, P4.4.
- **Observability Slice 1 — End-to-End-Tracing** (geplant, Plan abgenommen, Implementation offen).

## Referenz

- [`docs/`](docs/) — Doku-Index (Architektur, Deployment, Security, Operations)
- [`docs/runbooks/`](docs/runbooks/) — Detail-Runbooks (Tool-Pflicht, PR-Workflow, Worktree, Subagent-Routing, Layer)
- [`docs/STATUS.md`](docs/STATUS.md) — Test-Counts, Coverage, Milestones
- [`PLAN.md`](PLAN.md) — Operativer Slice-Plan
- [`CHANGELOG.md`](CHANGELOG.md) — Release-Notes
- [`CLAUDE.md`](CLAUDE.md) — Claude-spezifische Eigenheiten (Slash-Commands, MCP-Hooks)
