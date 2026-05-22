# [Jules][provider][backend][frontend] Unify provider naming (`gemini` vs `google`) across contracts and runtime

Master issue: Master audit 2026-05-22.

## Problem
Provider naming is inconsistent between frontend and backend runtime/provider registry.

## Evidence
- `backend/app/services/llm_runtime.py` lines 20-29, 115-120
- `backend/app/services/llm_provider_registry.py` lines 46-49
- `frontend/src/contracts/llmProfileContract.ts` provider literal set

## Scope
- Canonical provider enum in shared contract
- Backward-compatible input aliasing
- API responses standardized to canonical names

## Acceptance Criteria
- [ ] One canonical provider name for Gemini across API request/response payloads
- [ ] Legacy aliases still accepted for one release window
- [ ] Frontend Zod contracts updated and passing
- [ ] Backend contract tests added/updated
