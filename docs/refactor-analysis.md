# Refactor Analysis

## Current Architecture Overview
The Agora application is a local-first, multi-agent simulation engine built on Flask, Vue 3, and Neo4j. The backend structure has already undergone partial refactoring as described in `docu/target-architecture.md`, migrating to a DI-based architecture (`AgoraContainer`) with segmented API and Service layers. The frontend remains heavily coupled in some areas and primarily uses Vue options API/composition API without Pinia.

### Backend
- **Framework:** Flask with application factory and custom DI container.
- **Layers:** HTTP API (`api/`), Services (`services/`), Storage (`storage/`), Utilities (`utils/`).
- **Dependencies:** Neo4j, Ollama, Redis (hybrid event bus).
- **Subprocesses:** OASIS agents run as separate processes communicating via file/Redis IPC.

### Frontend
- **Framework:** Vue 3 with Vite.
- **State Management:** Mix of global reactive refs (`store/pendingUpload.js`), and component-local state. Custom composables (`usePolling.js`, `useEventStream.js`).
- **API Client:** Axios wrapped in simple services (`api/`).

### Docker/DevOps
- `docker-compose.yml` provides the environment, including `redis:7-alpine`.
- `.env.example` provides default configuration.

## Identified Issues

### Backend
- Monolithic API modules that need further decomposition (e.g., `simulation.py` compatibility layer).
- Mixed responsibilities in API routes (business logic vs. request handling).
- Error handling inconsistencies and non-standard response structures across legacy routes.
- Hardcoded configuration values and unvalidated inputs in older modules.
- The storage layer relies heavily on nested logic and lacks clear repository boundaries.

### Frontend
- Component structure is dense and sometimes mixes API calls with UI logic.
- Redundant fetch logic across components.
- Inconsistent error and loading state management.
- Hardcoded strings and magic numbers.

### DevOps & Security
- Default `.env` values are not inherently secure out-of-the-box.
- Need to ensure no secrets are checked into the repository.
- Dockerfile/compose configurations could be optimized for local development and reproducibility.
- Security review is pending (CORS, SSRF, Command Injection risks).

## Risks
- Breaking the OASIS simulation subprocesses due to IPC changes.
- Disrupting the GraphRAG ingestion pipeline.
- Introducing regressions in the frontend's Vue 3 reactivity system.

## Refactoring Plan
1. **Security & DevOps:** Create `docs/security-review.md`. Update `.env.example` and Docker configs.
2. **Backend Structure:** Move towards strict repository pattern. Ensure consistent API envelopes. Validate inputs. Clean up logging.
3. **Frontend Structure:** Centralize API calls. Improve component modularity. Implement clean loading/error states.
4. **Testing:** Ensure all 251 backend tests continue to pass and add tests for modified components.

## Proposed PR/Commit Splits
1. **Security & Config:** Initial security hardening and Docker config cleanup.
2. **Backend Core:** API response standardization and Service/Repository separation.
3. **Backend Logic:** Refactoring simulation and graph API routes.
4. **Frontend API:** Centralizing API logic and state management.
5. **Frontend Components:** Component cleanup and modularization.

## Changes Made
- Hardened Docker configuration by explicitly binding to `127.0.0.1` instead of `0.0.0.0`.
- Ensured `.env.example` does not encourage using default or empty values for `SECRET_KEY` and `NEO4J_PASSWORD`.
- Mitigated command injection risks in `SimulationRunner` by ensuring `max_rounds` is strongly typed to `int`.
- Cleaned up redundant compatibility module `backend/app/api/simulation.py`.
- Enforced uniform API response structures (`json_success` / `json_error`) across `simulation_interviews.py` and `simulation_run.py`.
- Improved error handling in Vue components by preventing silent failures in `catch` blocks within `SimulationRunView.vue`.
- Cleaned up redundant catch blocks in `MainView.vue` relying on central global interceptors.
