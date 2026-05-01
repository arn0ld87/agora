A previous agent produced the plan below to accomplish the user's task. Implement the plan in a fresh context. Treat the plan as the source of user intent, re-read files as needed, and carry
  the work through implementation and verification.

  # Agora v0.next: Run Center, Evidence Inspector, Scenario Branching

  ## Summary
  Implement the next increment around three connected features:

  - **Run History + Resume Center** as the single operational cockpit for graph builds, simulation prep/runs, and report generation.
  - **Report Evidence Inspector** to make every generated report auditable down to tool calls, facts, interviews, and optional web lookups.
  - **Scenario Branching** to fork an existing prepared simulation into a new branch with controlled overrides for fast what-if analysis.

  This plan intentionally extends the current file-backed architecture instead of replacing it. Existing artifacts such as `state.json`, `run_state.json`, `simulation_config.json`, `meta.json`,
  `progress.json`, `agent_log.jsonl`, and console logs remain source of truth; the new layer adds indexing, normalization, and UI composition on top.

  ## Key Changes

  ### 1. Run History + Resume Center
  Backend:
  - Add a new **Run Registry** service that indexes all long-running work into a persistent file-backed manifest under `backend/uploads/run_registry/`.
  - Define a normalized `run_manifest.json` per run with:
    - `run_id`
    - `run_type`: `graph_build` | `simulation_prepare` | `simulation_run` | `report_generate`
    - `entity_id`: `project_id`, `simulation_id`, or `report_id`
    - `parent_run_id` for derived runs
    - `status`: `pending` | `processing` | `paused` | `completed` | `failed` | `stopped`
    - `progress`, `message`, `error`
    - `started_at`, `updated_at`, `completed_at`
    - `artifacts`
    - `resume_capability`
    - `branch_label`
    - `metadata`
  - Keep `TaskManager` for in-process updates, but mirror task lifecycle changes to the Run Registry so status survives backend restarts.
  - Register graph build, simulation prepare, simulation run, and report generation through one shared run-recording API instead of each subsystem exposing its own partial state.
  - Add a new API namespace:
    - `GET /api/runs`
    - `GET /api/runs/<run_id>`
    - `GET /api/runs/<run_id>/events`
    - `POST /api/runs/<run_id>/resume`
    - `POST /api/runs/<run_id>/stop`
  - Map resume semantics explicitly:
    - `graph_build`: no true resume; offer `restart`
    - `simulation_prepare`: if required artifacts are partial, continue from last finished stage; else `restart`
    - `simulation_run`: if `state.json` and `simulation_config.json` are valid and runner is `paused` or `stopped`, resume via existing runner controls
    - `report_generate`: if sections already exist, continue from last incomplete section; otherwise restart
  - Replace current report-status fallback behavior with run-specific resolution first; old endpoints remain but internally consult the registry.

  Frontend:
  - Replace the current homepage history list with a richer **Run Center** view grouped by project and branch.
  - Each row shows run type, status, percent, last update, linked artifacts, and available actions.
  - Add filters for `project`, `run_type`, `status`, and `branch`.
  - Clicking a row opens the appropriate existing screen plus a run details drawer rather than a dead-end list item.

  ### 2. Report Evidence Inspector
  Backend:
  - Extend report generation so every section writes a machine-readable evidence map alongside existing markdown.
  - Add per-report artifact:
    - `evidence_map.json`
    - shape:
      - `report_id`
      - `simulation_id`
      - `sections[]`
      - each section contains `section_index`, `section_title`, `claims[]`
      - each claim contains `claim_id`, `claim_text`, `evidence_items[]`, `confidence`, `notes`
  - Evidence item types:
    - `graph_fact`
    - `entity_summary`
    - `relationship_chain`
    - `agent_interview`
    - `web_search_result`
    - `web_fetch`
    - `model_generated_inference`
  - During tool execution in `ReportAgent`, capture structured evidence candidates before they are flattened into plain text.
  - During section finalization, attach the candidate evidence used in that section to the section’s evidence map. Do not attempt perfect NLP claim extraction in v1; claim granularity is
  paragraph-level or bullet-level from generated section chunks.
  - Add new endpoints:
    - `GET /api/report/<report_id>/evidence`
    - `GET /api/report/<report_id>/evidence/<section_index>`
    - `GET /api/report/<report_id>/evidence/<section_index>/<claim_id>`
  - Keep existing `agent-log` and `console-log` endpoints; the inspector links to them rather than duplicating log streaming.

  Frontend:
  - Extend `Step4Report.vue` with a split mode:
    - report content on the left
    - evidence inspector on the right
  - Each rendered section gets an “Evidence” toggle.
  - Evidence panel shows:
    - section summary
    - claim cards
    - source type badges
    - original retrieved snippets
    - links to matching agent-log entries
  - Mark claims that rely mainly on `model_generated_inference` without direct retrieval as lower confidence.
  - Add an export option for `evidence_map.json`.

  ### 3. Scenario Branching
  Backend:
  - Add the concept of a **scenario branch** at the simulation level.
  - A branch is a new simulation directory derived from an existing prepared simulation without mutating the source branch.
  - New API:
    - `POST /api/simulation/<simulation_id>/branch`
    - `GET /api/simulation/<simulation_id>/branches`
  - Branch request payload:
    - `branch_name`
    - `copy_profiles`: default `true`
    - `copy_report_artifacts`: default `false`
    - `overrides` object with allowed fields only:
      - `llm_model`
      - `language`
      - `max_agents`
      - `time_config`
      - `enable_twitter`
      - `enable_reddit`
      - `persona_additions`
      - `persona_removals`
  - Branch creation behavior:
    - create new `simulation_id`
    - copy `simulation_config.json`
    - copy persona files
    - copy immutable preparation artifacts only
    - do not copy `run_state.json`, `control_state.json`, action logs, or console logs
    - write branch metadata into `state.json` and Run Registry
  - Track lineage:
    - `source_simulation_id`
    - `root_simulation_id`
    - `branch_name`
    - `branch_depth`
  - Validate overrides against an allowlist; unknown override keys are rejected.
  - Simulation history and run listings include branch metadata so comparison and filtering work later.

  Frontend:
  - Add “Create Branch” action from:
    - simulation detail
    - run center
    - report view
  - Branch dialog exposes only the approved overrides, not raw JSON editing in v1.
  - After branch creation, route to the new simulation’s setup view with visible lineage banner: “Derived from sim_xxx / branch_name”.

  ### 4. Shared Data and Compatibility Decisions
  - Do not introduce a database for run indexing in this phase.
  - Use file-backed manifests plus lightweight in-memory caching.
  - Add a shared `artifact_locator` helper so APIs do not keep re-implementing filesystem traversal for reports and simulations.
  - Keep existing endpoints and UI flows working; the new registry and branch APIs are additive.
  - Normalize status wording across subsystems to one canonical vocabulary in API responses.
  - All new identifiers remain existing-style prefixed IDs; no UUID format change.

  ## Public API / Interface Additions
  Backend HTTP:
  - `GET /api/runs`
  - `GET /api/runs/<run_id>`
  - `GET /api/runs/<run_id>/events`
  - `POST /api/runs/<run_id>/resume`
  - `POST /api/runs/<run_id>/stop`
  - `GET /api/report/<report_id>/evidence`
  - `GET /api/report/<report_id>/evidence/<section_index>`
  - `GET /api/report/<report_id>/evidence/<section_index>/<claim_id>`
  - `POST /api/simulation/<simulation_id>/branch`
  - `GET /api/simulation/<simulation_id>/branches`

  New file artifacts:
  - `backend/uploads/run_registry/<run_id>.json`
  - `backend/uploads/reports/<report_id>/evidence_map.json`

  Extended existing payloads:
  - simulation list/history entries gain:
    - `source_simulation_id`
    - `root_simulation_id`
    - `branch_name`
    - `branch_depth`
  - report detail gains:
    - `has_evidence`
    - `evidence_sections`
  - run detail exposes:
    - `artifacts`
    - `resume_capability`
    - `linked_ids`

  ## Test Plan
  Backend unit/integration:
  - Run Registry persists and reloads across process restart.
  - Existing graph build, simulation prepare, simulation run, and report generation all produce registry entries.
  - `resume` endpoint returns correct capability per run type.
  - Branch creation copies only intended artifacts and never mutates source simulation files.
  - Branch overrides apply only to allowlisted fields.
  - Report evidence generation writes valid `evidence_map.json` for completed reports.
  - Evidence endpoints handle missing/partial reports cleanly.
  - Old endpoints such as `/api/simulation/history` and `/api/report/generate/status` still work.

  Frontend:
  - Run Center renders mixed run types and filters correctly.
  - Report screen can open evidence for a section without breaking polling.
  - Branch dialog creates a new scenario and routes correctly.
  - Start report generation, restart backend, reload UI, confirm run still appears with persisted state.
  - Pause a simulation, resume it from Run Center, verify rounds continue.
  - Branch a prepared simulation, change model and max agents, confirm source config remains unchanged.
  - Generate a report and inspect evidence for a section that used graph retrieval plus interviews.
  - Generate a report with web tools disabled and verify evidence still works without web entries.
  - `context7` and a dedicated `sequential-thinking` tool are not available in this session; this plan is grounded in the checked repo state and current architecture.
  - v1 evidence mapping is section-chunk based, not sentence-perfect citation extraction.
  - v1 branching targets prepared simulations, not raw projects or unfinished graph builds.
  - v1 resume is capability-aware and honest; where true continuation is unsafe, the UI will present restart instead of pretending resume exists.
  - Existing file-backed storage remains the architectural baseline for this phase.
