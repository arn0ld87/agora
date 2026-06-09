# Agora Security & Architecture Review Report

## 1. SECRETS & CONFIG (P0)
- **Finding**: `SECRET_KEY` was not enforced during application startup in production mode (`FLASK_DEBUG=false`).
- **Action**: Modified `backend/app/__init__.py` to call `Config.validate()` and raise a `RuntimeError` if critical configuration is missing.
- **Status**: Fixed.

## 2. FILE UPLOAD SECURITY (P0/P1)
- **Finding**: `allowed_file` check was present but not strictly enforced for every file in the multipart upload loop.
- **Finding**: Lack of defensive path traversal checks in `ProjectManager.save_file_to_project`.
- **Action**: Updated `backend/app/api/graph.py` to strictly use `allowed_file`. Added `validate_project_id` and absolute path prefix checks in `backend/app/models/project.py`.
- **Status**: Fixed.

## 3. SUBPROCESS & SHELL EXECUTION (P0)
- **Finding**: `SimulationRunner` uses `subprocess.Popen` with a list of arguments and `shell=False`.
- **Action**: Verified that `cmd` is always a list and `start_new_session=True` is used for clean termination. User-controlled `simulation_id` is validated via regex before use.
- **Status**: Verified safe.

## 4. NEO4J & GRAPH INJECTION (P1)
- **Finding**: `get_nodes_by_label` used a local regex instead of the more robust `_sanitize_label` helper.
- **Action**: Refactored `backend/app/storage/neo4j_storage.py` to use `_sanitize_label`.
- **Status**: Fixed.

## 5. LLM CLIENT & OUTPUT HANDLING (P1)
- **Finding**: Regex for stripping `<think>` blocks and Markdown code fences was sensitive to case and whitespace.
- **Action**: Updated `backend/app/utils/llm_client.py` with case-insensitive and more robust regex patterns.
- **Status**: Fixed.

## 6. DOCKER & ISOLATION (P1)
- **Finding**: `Dockerfile` already implements a non-root `agora` user and `HEALTHCHECK`.
- **Action**: Verified `HEALTHCHECK` points to the correct `/health` endpoint on port 5001.
- **Status**: Verified safe.

## Summary & Effort Estimates
| Task | Complexity | Effort |
|------|------------|--------|
| Config Hardening | Low | S |
| File Upload Security | Low | S |
| Cypher Injection Fix | Low | S |
| LLM Sanitization | Low | S |
| Security Verification | Medium | S |

**Total Effort Estimate**: S (Completed)
