# P0.1b — Auth-Mode-Logging

**Datum:** 2026-04-29
**Slice:** P0.1b (siehe `PLAN.md`)
**Branch:** `security/repo-hardening`

## Ziel

`log_auth_mode` muss mit dem neuen `AGORA_ALLOW_ANONYMOUS`-Flag konsistent sein und beim Start eindeutig zeigen, in welchem Auth-Modus das Backend läuft.

## Änderungen

- `backend/app/utils/auth.py` — `log_auth_mode` unterscheidet vier Pfade:
  - Token gesetzt → `INFO`
  - Allow-Flag explizit → `WARNING` (opt-in offen)
  - Debug aktiv ohne Token → `WARNING` (lokale Entwicklung)
  - Sonst → `ERROR` (sollte von `Config.validate()` blockiert worden sein)
- Neuer Helper `_allow_anonymous()` zentralisiert die Truthy-Erkennung.
- `backend/tests/test_auth.py` erweitert um 4 Logging-Cases mit `_ListHandler`.

## Verifikation

- `uv run pytest tests/test_auth.py` → 10/10 grün.
- `uv run pytest` Full-Suite → 302 passed, 2 skipped.
- `uv run ruff check app/utils/auth.py tests/test_auth.py` → clean.

## Status

**Erledigt 2026-04-29.**
