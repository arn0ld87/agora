# [Jules][refactor][frontend][backend] Centralize SSE reconnect/retry configuration and behavior

Master issue: Master audit 2026-05-22.

## Problem
Retry/poll/reconnect behavior is duplicated across backend SSE endpoints and frontend stream composables.

## Evidence
- `backend/app/api/logs.py` (`_SSE_RETRY_MS` and stream loop)
- `backend/app/api/simulation_stream.py` (`_SSE_RETRY_MS`, `_POLL_INTERVAL`)
- `backend/app/api/settings.py` (`_SSE_RETRY_MS`)
- `frontend/src/composables/useEventStream.ts` lines 22-25, 97-112

## Scope
- Shared backend SSE config module
- Frontend stream policy module
- Contract tests for reconnect semantics

## Acceptance Criteria
- [ ] One backend source of truth for SSE retry constants
- [ ] Frontend reconnect policy is configurable and documented
- [ ] SSE behavior tests cover reconnect + stale ticket flows
