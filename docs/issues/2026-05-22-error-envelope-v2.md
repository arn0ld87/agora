# [Jules][bug][backend][frontend] Introduce normalized API error envelope v2 and migrate key routes

Master issue: Master audit 2026-05-22.

## Problem
Backend emits flat error envelopes; frontend infers retryability/timeouts heuristically.

## Evidence
- `backend/app/utils/api_responses.py` lines 149-156
- `frontend/src/api/index.ts` lines 71-131

## Scope
- Add `{ error: { code, message, provider?, retryable?, details? } }` envelope
- Keep temporary compatibility for old clients
- Update frontend parser to trust backend error metadata

## Acceptance Criteria
- [ ] Backend helper emits v2 envelope for migrated routes
- [ ] Frontend consumes v2 and preserves UX messaging
- [ ] Timeout/retryable/provider fields set for provider errors
- [ ] API contract docs updated
