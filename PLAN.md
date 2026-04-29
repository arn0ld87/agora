# PLAN.md — P0 Security Hardening (REFACTORING_PLAN.md)

**Datum:** 2026-04-29 (Europe/Berlin)
**Branch-Konvention:** `security/repo-hardening`
**Quelle:** `REFACTORING_PLAN.md` Tabelle, Priorität P0

## Ziel

Zwei P0-Punkte umsetzen, jeder als getrennter Sub-Slice mit 1 Commit + Arbeitsprotokoll:

1. Auth außerhalb `FLASK_DEBUG=true` standardmäßig erzwingen, opt-out via Allow-Flag.
2. SSE/Download-Auth von langlebigem Query-Token auf kurzlebige signierte Tickets migrieren.

## Defaults (festgelegt)

- Allow-Flag-Name: `AGORA_ALLOW_ANONYMOUS=true` (Opt-out für Lab/Klassenraum-Setups).
- Ticket-TTL: 60 s, single-use, scope-bound.
- Ticket-Signatur: HMAC-SHA256 mit `SECRET_KEY` als Schlüssel.
- `?token=` Query-Pfad: in P0.2b mit Deprecation-Warning (Logger) weiter geduldet, Hard-Removal in Folge-Slice.

## Sub-Slices

### P0.1a — Config-Fail-Fast

- `backend/app/config.py::Config.validate()` ergänzen:
  - Wenn `not DEBUG` und kein `AGORA_AUTH_TOKEN` und kein `AGORA_ALLOW_ANONYMOUS=true` → Fehler `"AGORA_AUTH_TOKEN missing in non-debug mode (set AGORA_ALLOW_ANONYMOUS=true to opt out)"`.
- Doku: `.env.example` (falls vorhanden), `CLAUDE.md`, `AGENTS.md` synchron um `AGORA_ALLOW_ANONYMOUS` ergänzen.
- Tests: `tests/test_config_validate.py` neu mit drei Fällen (debug allow, prod ohne Token Fail, prod mit Allow-Flag OK, prod mit Token OK).

**Commit:** `feat(security): enforce auth in non-debug mode unless ALLOW_ANONYMOUS`
**Arbeitsprotokoll:** `docu/2026-04-29-p0-1a-auth-fail-fast.md`

### P0.1b — Auth-Mode-Logging

- `log_auth_mode` in `utils/auth.py`:
  - Im offenen Modus erkennt es `AGORA_ALLOW_ANONYMOUS=true` und loggt explizit "anonymous mode opt-in", sonst weiterhin Warning.
- Tests: `test_auth.py` — Log-Capture für die drei Pfade (token gesetzt / allow-flag / nichts).

**Commit:** `chore(security): clarify auth-mode logging for anonymous opt-in`
**Arbeitsprotokoll:** `docu/2026-04-29-p0-1b-auth-mode-log.md`

### P0.2a — Signed-Ticket-Util

- Neu: `backend/app/utils/signed_ticket.py`
  - `issue(scope: str, ttl_seconds: int = 60) -> str` → Ticket-String `v1.<exp>.<scope>.<sig>`.
  - `verify(ticket: str, scope: str) -> bool` → prüft Signatur, Ablauf, Scope; markiert verbrauchtes Ticket in `seen`-Set mit Expiry-Sweep.
  - Schlüssel: `current_app.config["SECRET_KEY"]`.
- Tests: `tests/test_signed_ticket.py` — gültig, abgelaufen, falscher Scope, doppelte Verwendung, manipulierte Signatur.

**Commit:** `feat(security): add signed-ticket utility for short-lived URL auth`
**Arbeitsprotokoll:** `docu/2026-04-29-p0-2a-signed-tickets.md`

### P0.2b — Auth-Endpoint + Ticket-Pfad

- Neu: `POST /api/auth/ticket` (Bearer/Header-auth zwingend), Body `{"scope":"sse:<sim>"}`, Response `{"ticket","exp"}`.
- `_extract_token()`:
  - Fügt `?ticket=`-Pfad ein → `verify(ticket, scope=request.path-derived)`. Wenn valid → erlauben, ohne Token-Vergleich.
  - `?token=` bleibt aber loggt einmal pro Request `deprecation: query-token`.
- Tests: Endpoint + Guard mit Ticket-Pfad.

**Commit:** `feat(security): /api/auth/ticket and ticket-aware request auth`
**Arbeitsprotokoll:** `docu/2026-04-29-p0-2b-ticket-endpoint.md`

### P0.2c — Frontend-Umstellung

- `frontend/src/api/index.js`: Helper `requestStreamTicket(scope)` und `requestDownloadTicket(scope)`.
- `frontend/src/api/stream.js`: vor `new EventSource(...)` Ticket holen, `?ticket=` statt `?token=`.
- Download-Aufrufe (`download_simulation_config`, `download_simulation_script`, `download_report`) auf Ticket-URL umstellen — entweder über `<a href>` mit ticket-URL oder `fetch + blob`.
- Smoke: SSE öffnen, Report-Download triggern.

**Commit:** `feat(security): frontend uses signed tickets for SSE and downloads`
**Arbeitsprotokoll:** `docu/2026-04-29-p0-2c-frontend-tickets.md`

## Verifikation pro Sub-Slice

- `cd backend && uv run pytest <neue_test_datei>` (geschnittene Suite, dann Full Suite vor Commit).
- `npm run check` als Gate vor Push.
- E2E-Smoke nur P0.2c: `npm run dev`, SSE und Report-Download manuell testen.

## Risiken & Rollback

- P0.1a: Hartes Startup-Fail kann existierende Deployments brechen → Allow-Flag deckt das ab, klar in Release-Notes.
- P0.2b/c: `?token=`-Pfad bleibt zunächst funktional → Rollback ist `revert <commit>`, keine Datenmigration.
- Single-Use-Ticket-Set lebt im Prozess-Speicher: bei Multi-Worker-Deployment kann dasselbe Ticket bei jedem Worker einmal verbraucht werden. Akzeptabel solange TTL klein und Scope eng. Folge-Ticket: optional Redis-backed `seen`-Set.
