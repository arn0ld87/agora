# Follow-up Issues: Agora Repository Audit (May 2026)

This document tracks actionable improvements identified during the comprehensive repository audit.

## [ISSUE-01] Refactor: Centralize LLM Context Heuristics
- **Label:** Jules, refactor, backend
- **Files:**
  - `backend/app/utils/llm_client.py`
  - `backend/scripts/agent_tools.py`
  - `backend/scripts/_sim_common.py`
- **Problem:** Model context heuristics (the `_MODEL_CONTEXT_HEURISTICS` table and its resolution logic) are duplicated across three locations. This leads to drift and inconsistent context window behavior between the API and simulation subprocesses.
- **Acceptance Criteria:**
  - Heuristics moved to a shared module (e.g., `backend/app/utils/llm_heuristics.py`).
  - Both `LLMClient` and OASIS scripts use the centralized resolver.
  - Tests verify that all consumers receive the same limits for a given model.
- **Risk:** Medium (affects context truncation)

## [ISSUE-02] Refactor: Unify Simulation Logic in `run_parallel_simulation.py`
- **Label:** Jules, refactor, backend
- **Files:**
  - `backend/scripts/run_parallel_simulation.py`
- **Problem:** `run_twitter_simulation` and `run_reddit_simulation` are nearly identical, duplicating ~200 lines of boilerplate for model creation, tool attachment, and loop management.
- **Acceptance Criteria:**
  - Platforms refactored into a unified `run_platform_simulation` function.
  - Platform-specific differences (action lists, DB filenames) passed as configuration.
- **Risk:** Low

## [ISSUE-03] Frontend: Implement `AbortController` for API Requests
- **Label:** Jules, frontend, backend
- **Files:**
  - `frontend/src/api/index.ts`
  - `frontend/src/api/*.ts`
- **Problem:** Long-running LLM tasks (ontology generation, report synthesis) cannot be cancelled from the UI. This leaves background requests hanging and wastes provider tokens.
- **Acceptance Criteria:**
  - Axios instance supports passing an `AbortSignal`.
  - Main API functions accept an optional `signal`.
  - UI components (Wizard, RunDetail) provide "Cancel" buttons that trigger the abort.
- **Risk:** Medium

## [ISSUE-04] Code Quality: Remove unsafe `any` usages in Frontend
- **Label:** Jules, frontend
- **Files:** `frontend/src/**/*.ts`, `frontend/src/**/*.vue`
- **Problem:** 111 `any` types mask potential runtime errors and reduce IDE assistance.
- **Acceptance Criteria:**
  - `any` count reduced by at least 80%.
  - Critical boundaries (API responses, Pinia stores) are fully typed.
- **Risk:** Medium

## [ISSUE-05] Code Quality: Narrow broad `except Exception` blocks in Backend
- **Label:** Jules, backend
- **Files:** `backend/app/services/*.py`
- **Problem:** Overly broad exception handling hides logic errors and makes debugging difficult.
- **Acceptance Criteria:**
  - Service methods catch specific, expected exceptions.
  - Standardized logging for caught errors.
- **Risk:** Medium

## [ISSUE-06] Provider: Robust Gemini Tool Calling in `LLMClient`
- **Label:** Jules, provider, backend
- **Files:** `backend/app/utils/llm_client.py`
- **Problem:** Gemini requires `thought_signature` preservation in multi-turn tool calls. The current `LLMClient` OpenAI-compat path may strip these, causing 400 errors during complex ReACT loops in the report agent.
- **Acceptance Criteria:**
  - `LLMClient` detects Gemini and uses the native CAMEL adapter or preserves required fields.
- **Risk:** High (Gemini robustness)

## [ISSUE-07] Refactor: Decompose `Step3Simulation.vue`
- **Label:** Jules, refactor, frontend
- **Files:** `frontend/src/components/Step3Simulation.vue`
- **Problem:** At 1100+ lines, this component is a "God Component" that handles stats, feed, console, and state machine logic.
- **Acceptance Criteria:**
  - Logic extracted into smaller, testable components.
  - Main component reduced to < 500 lines.
- **Risk:** Low

## [ISSUE-08] Alignment: Modernize `LogDrawer.vue` Error Handling
- **Label:** Jules, frontend, alignment
- **Files:** `frontend/src/components/LogDrawer.vue`
- **Problem:** Uses legacy manual error parsing instead of the standardized `ApiError` + `unwrap()` pattern.
- **Acceptance Criteria:**
  - Consistent error UI matching other components.
- **Risk:** Low
