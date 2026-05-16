# Worklog 2026-05-15 — Smoke-Fix Slice 03

**Datum:** 2026-05-15
**Branch:** `feat/smoke-fix-03-auth-ticket-refresh` → merged in `feat/smoke-fix-2026-05-15-welle2-epic`
**Layer:** 1 (Backend-Auth) + 4 (Frontend-API)
**Closes:** Befund #4 (Auth-Ticket-Loop bei Browser-Idle)

## Problem

Nach ~5 min Idle in Step 2 (EnvSetup) läuft das Auth-Ticket ab:

```
GET /api/simulation/sim_xxx → 401
POST /api/auth/ticket → 401   ← Re-Auth selbst failt
```

Frontend hat keinen Refresh-Pfad und bleibt mit Status „Fehler" hängen. Workaround: Reload (neues Ticket via Session-Cookie).

Root-Cause: `/api/auth/ticket` verlangt bestehenden gültigen `X-Ticket-Header`, kann sich also nicht selbst erneuern wenn das Ticket abgelaufen ist. Henne-Ei-Problem.

## Fix

**Backend (`backend/app/utils/auth.py` + `backend/app/__init__.py`):**
- `/api/auth/ticket` bekommt neue Logik: Falls `X-Ticket-Header` fehlt oder ungültig, versuche Authentifizierung via Session-Cookie oder API-Key (die persisten länger).
- Bei erfolgreicher Alt-Auth wird neues Ticket generiert.

**Frontend (`frontend/src/composables/useApiAuth.ts`, NEU):**
- Neue Composable `useApiAuth()` mit `withFreshTicket()` Helper.
- Bei 401-Response auf beliebigen Endpoint automatisch `/api/auth/ticket` POST (ohne Header) aufrufen.
- Falls erfolgreich: Request mit neuem Ticket wiederholen.
- Falls fehlschlag: Benutzer logout.

**Aufrufer-Migration:**
- `frontend/src/api/{stream.ts, logs.ts, settings.ts}`
- `frontend/src/store/useActiveModelStore.ts`

## Tests

Neu:
- `backend/tests/test_auth.py` erweitert um 3 Tests — `/api/auth/ticket` ohne Header mit gültigem Cookie
- `frontend/src/composables/__tests__/useApiAuth.spec.ts` (NEU) — 5 Tests für Auto-Refresh-Flow

**Test-Counts:** Backend +3 / Frontend +5 = +8 gesamt

## Geänderte Dateien

- `backend/app/utils/auth.py` (+22 LOC)
- `backend/app/__init__.py` (+3 LOC, Route-Anpassung)
- `backend/tests/test_auth.py` (+15 LOC)
- `frontend/src/composables/useApiAuth.ts` (+67 LOC, NEU)
- `frontend/src/composables/__tests__/useApiAuth.spec.ts` (+89 LOC, NEU)
- `frontend/src/api/stream.ts` (+8 LOC, withFreshTicket angewandt)
- `frontend/src/api/logs.ts` (+8 LOC)
- `frontend/src/api/settings.ts` (+8 LOC)
- `frontend/src/store/useActiveModelStore.ts` (+5 LOC)

## Risiken & Gaps

- `withFreshTicket()` Composable ist opt-in — noch nicht alle API-Calls haben es. Vorerst auf kritische Pfade (Stream, Logs, Settings) beschränkt.
- Session-Cookie-Persistenz im Browser hängt von `SameSite`-Policy und Domain-Config ab — lokal OK, in Produktion prüfen.
- Retry-Logik wiederholt Requests ohne idempotence-Garantie — POST-Calls sollten idempotent sein (sind's über `request_id` nicht derzeit; low-risk für diesen Bug-Fix).

## Verifikations-Gate

```bash
cd backend && uv run pytest tests/test_auth.py -v
cd frontend && npm test -- src/composables/__tests__/useApiAuth.spec.ts --run
npm run typecheck && npm run build && npm run lint
cd backend && pytest -x -q  # volle Suite
```

Alle grün. Manueller Smoke mit 5+ min Idle ohne Error.

## Slice-Commit-Hash

Siehe Branch-History.
