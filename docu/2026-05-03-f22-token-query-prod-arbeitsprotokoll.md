# Arbeitsprotokoll F2.2 — ?token= Query-Parameter in Prod deaktiviert

**Datum:** 2026-05-03  
**Slice:** M9-4 / F2.2  
**Subagent:** agora-refactor-worker (Sonnet)  
**Branch:** fix/f22-token-query-prod  
**Refs:** PLAN.md F2.2

## Problem

`?token=<bearer>` als Query-Parameter war seit P0.2 als Deprecation-Warning markiert, wurde aber in Prod-Umgebungen weiterhin akzeptiert. Das ist ein Sicherheitsrisiko (Token in URL = Browser-History, Server-Logs, Referrer).

## Aenderungen

### 1. `backend/app/utils/auth.py` — `_extract_token()`

```python
query_token = request.args.get("token", "")
if query_token:
    if not current_app.config.get("FLASK_DEBUG"):
        # In Prod: ?token= ist deaktiviert (F2.2). Signed-Tickets nutzen.
        _logger.error(...)
        return ""
    _logger.warning(...)
return query_token
```

In Prod (FLASK_DEBUG=false) wird `?token=` ignoriert und mit ERROR geloggt. Der normale Auth-Fehler-Mechanismus (401/403) greift dann.

### 2. `backend/tests/test_auth.py`

- `test_blueprint_guard_accepts_query_token` → umbenannt in `test_blueprint_guard_accepts_query_token_in_debug`
- Neu: `test_blueprint_guard_rejects_query_token_in_prod` — prüft 401 bei `?token=` wenn FLASK_DEBUG=false

## Akzeptanz

```bash
cd backend && uv run pytest tests/test_auth.py::test_blueprint_guard_rejects_query_token_in_prod -v
# → PASSED
cd backend && uv run pytest tests/test_auth.py -v
# → alle grün
```

## Offen

- Merge auf `main` nach 90s + CI-Prüfung.
- Nächster Slice: F3 (Gunicorn-Gevent-Migration).
