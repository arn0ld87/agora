# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Agora is a fully local fork of MiroFish: a multi-agent swarm-intelligence simulator. Upload a document → extract a knowledge graph → spawn hundreds of personality-driven agents → simulate social-media reactions → generate a report. The fork replaces Zep Cloud with Neo4j and DashScope/OpenAI with Ollama (or any OpenAI-compatible endpoint).

Stack: Flask (Python 3.11) + Vue 3 + Vite + Neo4j 5.18 CE + OASIS (`camel-oasis`) + Ollama. Package managers: `uv` for backend, `npm` for frontend.

## Expected tool usage (proactive — don't wait to be asked)

- **context7** — whenever a task touches a library, framework, SDK, CLI, or cloud service (Flask, Vue, Vite, Neo4j driver, OASIS/CAMEL, Ollama, Pinia-replacement patterns, OpenAI-compatible APIs, pytest, uv, etc.), query context7 to verify current syntax/config before writing or changing code. Do this even for APIs you "already know" — training data lags.
- **GitHub search** (WebFetch/WebSearch against github.com, or `gh`) — when debugging third-party behavior (OASIS quirks, Neo4j 5.18 vector search edge cases, Ollama tool-call payloads, etc.), check upstream issues/PRs for known fixes before designing a workaround.
- **sequential-thinking** — engage automatically for multi-file refactors, pipeline-spanning changes (graph → env → simulation → report), debugging that crosses subprocess boundaries, or any task where the solution path isn't obvious after a single read. Don't require an explicit "think step by step" from the user.

These three are defaults, not escalations. If skipping one, say why in-line.

## Commands

All commands run from repo root unless stated otherwise.

```bash
# First-time install (root npm + frontend npm + backend uv sync)
npm run setup:all

# Dev — runs backend (uv run python run.py) and frontend (vite) concurrently
npm run dev

# Individual processes
npm run backend        # Flask on :5001
npm run frontend       # Vite on :5173 (proxies /api → :5001)
npm run build          # Production frontend bundle

# Backend tests (pytest, optional dev group)
cd backend && uv run pytest
cd backend && uv run pytest path/to/test_file.py::test_name
```

Docker (full stack incl. Neo4j):

```bash
docker compose up -d
docker compose build agora && docker compose up -d --force-recreate --no-deps agora  # after code/env changes
docker logs -f agora
```

Neo4j Browser: http://localhost:7474 · Backend health: http://localhost:5001/health

## Configuration

All runtime config flows through `.env` at repo root, loaded by `backend/app/config.py`. Required: `LLM_API_KEY` (any non-empty string for Ollama, e.g. `ollama`), `NEO4J_URI`, `NEO4J_PASSWORD`. Important non-obvious knobs:

- `LLM_MODEL_NAME` — defaults to `qwen2.5:32b`. For Ollama Cloud, `qwen3-coder-next:cloud` is the recommended model (see `docs/graphrag-speedup.md`).
- `OLLAMA_THINKING=false` — strips reasoning blocks for Qwen3/GPT-OSS/DeepSeek-R1 (handled in `utils/llm_client.py`).
- `LLM_DISABLE_JSON_MODE=true` — disables `response_format=json_object`; markdown fences are stripped in `chat_json()`.
- `GRAPH_CHUNK_SIZE=1500`, `GRAPH_CHUNK_OVERLAP=150`, `GRAPH_PARALLEL_CHUNKS=4` — graph-build performance (sweet spot for Ollama Cloud).
- `REPORT_LANGUAGE=German` — output language for ReportAgent.
- `TIME_PROFILE=dach_default` — DACH / Europe-Berlin social activity timing defaults.
- `ENABLE_AGENT_TOOLS=false` — experimental OASIS agent tool-use is opt-in; enabling it adds LLM calls and latency.

## Architecture

### Backend layering (DI via `app.extensions`, no globals)

`Flask app (create_app)` → registers three blueprints under `/api/{graph,simulation,report}` and stores a single `Neo4jStorage` instance in `app.extensions['neo4j_storage']`. Endpoints pull the storage from there; services receive it via constructor.

```
api/        thin HTTP layer (graph.py, simulation.py, report.py)
services/   business logic — graph_builder, simulation_manager,
            simulation_runner (subprocess), report_agent, etc.
storage/    GraphStorage abstract → Neo4jStorage impl,
            EmbeddingService (Ollama), NERExtractor (LLM), SearchService (hybrid)
utils/      llm_client (OpenAI-compatible wrapper with Ollama tweaks),
            file_parser (PDF/MD/TXT), logger, retry
models/     dataclasses (Project, Task)
```

`GraphStorage` is the swap point — replace `Neo4jStorage` and the rest of the app keeps working. `SearchService` uses hybrid scoring `0.7 * vector + 0.3 * BM25`; vector dim = 768 (`nomic-embed-text`).

### The four-stage pipeline

1. **Graph build** (`services/graph_builder.py`) — chunk document → parallel `ThreadPoolExecutor` of `storage.add_text` calls (LLM NER/RE per chunk → embeddings → Neo4j). Parallelism gated by `GRAPH_PARALLEL_CHUNKS`.
2. **Env setup** (`services/oasis_profile_generator.py`, `simulation_config_generator.py`) — generates persona JSON for OASIS. Persona/config is **frozen** into `uploads/simulations/<sim_id>/simulation_config.json`; runtime `.env` changes do NOT propagate to a prepared simulation (see speedup doc for the patch recipe).
3. **Simulation** (`services/simulation_runner.py`, `scripts/run_*_simulation.py`) — OASIS runs in a **separate subprocess** (Twitter/Reddit/parallel scripts under `backend/scripts/`). IPC via `simulation_ipc.py` and `run_state.json` files. `SimulationRunner.register_cleanup()` is wired into Flask startup to kill orphans on shutdown.
4. **Report** (`services/report_agent.py`) — tool-using agent that queries `GraphToolsService` (graph search, agent interview, panorama). Loop limits: `REPORT_AGENT_MAX_TOOL_CALLS`, `REPORT_AGENT_MAX_REFLECTION_ROUNDS`.

### Frontend (Vue 3 + Vite)

`frontend/src/views/` contains one component per pipeline stage (`Process`, `SimulationView`, `SimulationRunView`, `ReportView`, `InteractionView`). API helpers in `src/api/` mirror the three blueprints. Vite dev server proxies `/api` → `localhost:5001`, so the frontend code uses relative `/api/...` paths. Pinia is **not** used — state lives in a single `src/store/pendingUpload.js` module.

## Conventions & gotchas

- Neo4j must be **5.18+** for relationship vector search (pinned in `docker-compose.yml`; do not downgrade).
- The OASIS subprocess inherits env from the Python process, so backend env updates take effect only after a backend restart, **not** a Flask reload.
- File uploads land in `backend/uploads/`; simulations under `backend/uploads/simulations/<sim_id>/`. The Docker volume mounts only `backend/uploads`.
- Backend allowed extensions: `pdf`, `md`, `txt`, `markdown`. `MAX_CONTENT_LENGTH = 50 MB`.
- Some upstream Chinese references may remain in attribution or migration inventories, but runtime prompts/defaults should not assume non-DACH user behavior.

## Reference

`docs/graphrag-speedup.md` — concrete recipe for getting graph-build under one minute against Ollama Cloud (model choice, thinking-flag, JSON mode, chunk size/parallelism, plus Docker recreate footguns and the simulation-config patch trick). Read this before touching `graph_builder.py`, `llm_client.py`, or anything that calls Ollama.

`docs/agent-tools-integration.md` — how OASIS agents are wired to `GraphToolsService` / `WebTools` when `ENABLE_AGENT_TOOLS=true`.
