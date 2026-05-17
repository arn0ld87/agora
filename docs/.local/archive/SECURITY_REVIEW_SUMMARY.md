# Security Review Summary: Agora Backend

> **Stand 2026-04-22:** Teile dieses Dokuments sind durch die in
> [`security-hardening.md`](./security-hardening.md) umgesetzten Phasen 1–3
> überholt (insbesondere CORS/Auth aus Punkt 6). Diese Datei bleibt als
> historischer Review-Snapshot erhalten.

## 1. SECRETS & CONFIG (P0)
- **Status:** Partially remediated.
- **Findings:** No hardcoded production API keys found in the code. `.env.example` contains default placeholders.
- **Fixes:** Added security warning in `backend/app/config.py` when using default `SECRET_KEY` in production.
- **Effort Estimate:** S

## 2. FILE UPLOAD SECURITY (P0/P1)
- **Status:** Remediated.
- **Findings:** `MAX_CONTENT_LENGTH` is enforced by Flask. Extension check was present but basic.
- **Fixes:** Added `secure_filename` sanitization in `ProjectManager`. Added basic magic number check for PDF files in `allowed_file`.
- **Effort Estimate:** S

## 3. SUBPROCESS & SHELL EXECUTION (P0)
- **Status:** Verified Safe.
- **Findings:** `SimulationRunner` uses `subprocess.Popen` with a list of arguments and `shell=False` (implicit), which prevents shell injection. Commands are constructed using trusted local script paths.
- **Mitigation:** ID validation (see below) prevents using `simulation_id` for path traversal in subprocess-related paths.
- **Effort Estimate:** S

## 4. NEO4J & GRAPH INJECTION (P1)
- **Status:** Remediated.
- **Findings:** Most queries were parameterized. One instance of f-string label injection was found.
- **Fixes:** Added regex-based sanitization for labels in `Neo4jStorage.get_nodes_by_label`.
- **Effort Estimate:** S

## 5. LLM CLIENT & OUTPUT HANDLING (P1)
- **Status:** Verified Safe.
- **Findings:** LLM responses are parsed using `json.loads` with defensive logic for truncated or malformed JSON. No use of `eval()` or `exec()` on LLM output found.
- **Effort Estimate:** S

## 6. CORS & API EXPOSURE (P1)
- **Status:** Punted / TODO.
- **Findings:** CORS is currently permissive (`*`). All API endpoints are unauthenticated.
- **TODO:** Added `TODO(JULES)` for origin restriction and authentication implementation.
- **Effort Estimate:** M/L

## 7. SIMULATION ISOLATION (P1/P2)
- **Status:** Partially remediated.
- **Findings:** Docker container was running as root. Concurrent simulations share Neo4j but are isolated by `graph_id`.
- **Fixes:** Modified `Dockerfile` to use a non-root `USER` and added a `HEALTHCHECK`.
- **Effort Estimate:** S

## 8. ERROR HANDLING & LOGGING (P2)
- **Status:** Remediated.
- **Findings:** Stack traces were exposed in API responses regardless of debug mode.
- **Fixes:** Modified all API error handlers to only return `traceback` if `Config.DEBUG` is True.
- **Effort Estimate:** S

## 9. PATH TRAVERSAL (P0)
- **Status:** Remediated.
- **Findings:** Risk of path traversal via `project_id`, `simulation_id`, or `report_id`.
- **Fixes:** Implemented centralized ID validation in `backend/app/utils/validation.py` and applied it to all relevant API endpoints.
- **Effort Estimate:** S
