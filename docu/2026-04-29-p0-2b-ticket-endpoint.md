# P0.2b — Auth-Endpoint und ?ticket= Pfad

**Datum:** 2026-04-29
**Slice:** P0.2b (siehe `PLAN.md`)
**Branch:** `security/repo-hardening`

## Ziel

Den langlebigen `?token=<bearer>`-URL-Pfad durch kurzlebige signierte Tickets ablösen. Endpoints, die URL-Auth brauchen (SSE, Downloads), markieren sich explizit als ticket-fähig — alles andere bleibt auf Header/Bearer.

## Änderungen

- `backend/app/utils/auth.py`
  - `allow_ticket_auth(scope_fn)` Decorator markiert View-Funktionen mit einer URL-Args→Scope-Ableitung.
  - Blueprint-Guard versucht Token zuerst, danach `?ticket=` für markierte Views via `signed_ticket.consume`.
  - `?token=` Query-Pfad emittiert eine `WARNING`-Logzeile (Deprecation-Hinweis).
- `backend/app/api/auth.py` (neu)
  - `POST /api/auth/ticket` mit Body `{"scope": "sse:<id>", "ttl_seconds": 60}` → `{"ticket","exp","scope"}`.
  - Whitelist erlaubter Scope-Präfixe (`sse:`, `download:report:`, `download:simulation_config:`, `download:simulation_script:`).
  - TTL clamp `(0, 300]` — kein Aussetzer bei Endlos-Tickets.
- `backend/app/api/__init__.py` registriert `auth_bp`.
- `backend/app/__init__.py` hängt `auth_bp` unter `/api/auth` ein und installiert den Token-Guard.
- Markierte Views:
  - `simulation_stream` → `sse:<simulation_id>`
  - `download_simulation_config` → `download:simulation_config:<simulation_id>`
  - `download_simulation_script` → `download:simulation_script:<script_name>`
  - `export_report`, `download_report` → `download:report:<report_id>`
- Doku: `CLAUDE.md`, `AGENTS.md` synchronisiert.
- `backend/tests/test_auth_ticket.py` (neu) — 8 Cases:
  1. Ticket-Endpoint ohne Bearer → 401
  2. Ticket-Endpoint mit Bearer + valid Scope → 200, `ticket`/`exp`/`scope` im Body
  3. Invalid Scope → 400 `invalid_scope`
  4. TTL > 300 → 400 `invalid_ttl`
  5. Guarded View mit valid Ticket → 200
  6. Ticket für andere Simulation → 401
  7. Replay des Tickets → zweiter Hit 401
  8. Ticket gegen View ohne `@allow_ticket_auth` → 401

## Verifikation

- `uv run pytest tests/test_auth_ticket.py` → 8/8.
- `uv run pytest` Full-Suite → 320 passed, 2 skipped.
- `uv run ruff check` auf allen geänderten Backend-Dateien → clean.

## Bekannte Lücken

- `?token=`-Query-Pfad bleibt bewusst funktional, emittiert nur eine Warning. Hard-Removal in einem Folge-Slice nach Frontend-Migration (P0.2c) und Telemetrie-Bestätigung „niemand hängt mehr dran".
- Single-Use-Set ist Process-local (siehe Hinweis in `signed_ticket.py`).

## Status

**Erledigt 2026-04-29.**
