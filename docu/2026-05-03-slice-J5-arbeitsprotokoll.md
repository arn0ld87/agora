# Arbeitsprotokoll Sub-Slice J.5 — SSE retry-Frame Hardening (#223)

**Datum:** 2026-05-03
**Branch:** `fix/task-J5-sse-retry`
**Worker:** agora-refactor-worker (Sonnet)

## Befund

Beide SSE-Endpoints sandten kein `retry:`-Feld:

- `backend/app/api/simulation_stream.py` (`_stream()` Generator)
- `backend/app/api/logs.py` (`gen()` nested Generator in `stream_logs()`)

Ohne dieses Feld nutzt der Browser seinen internen Default (~3 s, nicht vom
Backend steuerbar). `frontend/src/components/LogDrawer.vue:114` hatte einen
leeren `onerror`-Handler — Connection-Errors wurden geschluckt.

## Verifikation (Phase 1 — rg-Output)

```
simulation_stream.py: keine 'retry:'-Zeile vorhanden
logs.py: keine 'retry:'-Zeile vorhanden
LogDrawer.vue:114: _eventSource.onerror = () => { /* reconnect handled by browser */ }
settings_layer.py: SSE_RETRY/SSE_RECONNECT nicht vorhanden
```

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `backend/app/api/simulation_stream.py` | `_SSE_RETRY_MS = 5000` + `yield f"retry: {_SSE_RETRY_MS}\n\n"` als erstes Frame |
| `backend/app/api/logs.py` | `_SSE_RETRY_MS = 5000` + `yield f'retry: {_SSE_RETRY_MS}\n\n'` als erstes Frame |
| `frontend/src/components/LogDrawer.vue` | `onerror` befüllt mit `console.warn` + `appendLine(t('logs.drawer.connectionError'))` |
| `frontend/src/i18n/locales/de.json` | Key `logs.drawer.connectionError` hinzugefügt |
| `frontend/src/i18n/locales/en.json` | Key `logs.drawer.connectionError` hinzugefügt |
| `backend/tests/api/test_sse_retry_field.py` | Neuer Test-File (3 Tests) |
| `CHANGELOG.md` | `[Unreleased] → Fixed` ergänzt |

## Test-Strategie

- `simulation_stream`: Generator-Unit-Test (kein HTTP) — `next(_stream(sim_id))` liefert
  `retry: 5000\n\n` als erstes Frame, zweites Frame ist `event: hello`.
- `logs/stream`: Integration-Test via Flask-Test-Client — erster Chunk aus
  `response.response` Iterator enthält `retry: 5000`.

## Ergebnis

- 3 neue Tests PASS
- 1359 Backend-Tests gesamt: 1359 passed, 9 skipped
- mypy auf geänderten Dateien: clean
- ruff auf geänderten Dateien: clean
- Frontend: 18 test files, 146 tests passed, build success

## Offene Punkte

- `_SSE_RETRY_MS` ist aktuell hard-coded mit 5000 ms + TODO-Kommentar.
  Konfigurierbar über `settings_layer` sobald Sub-Slice D implementiert ist.

## Referenzen

- Issue: #223
- Hardstop: kein; Flask-Generator-Pattern erlaubt retry-Frame als normalen
  `yield str` ohne Einschränkung.
