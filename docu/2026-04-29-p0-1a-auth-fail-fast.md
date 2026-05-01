# P0.1a — Auth-Fail-Fast in Non-Debug

**Datum:** 2026-04-29
**Slice:** P0.1a (siehe `PLAN.md`)
**Branch:** `security/repo-hardening`

## Ziel

`Config.validate()` lehnt Start ab, wenn `FLASK_DEBUG=false`, kein `AGORA_AUTH_TOKEN` gesetzt und kein expliziter `AGORA_ALLOW_ANONYMOUS=true`. Damit ist „API offen in Prod" kein Default mehr, sondern eine bewusste Opt-out-Entscheidung.

## Änderungen

- `backend/app/config.py` — neuer Validierungspfad in `Config.validate()`.
- `backend/tests/test_config_validate.py` — neue Test-Datei mit 4 Fällen.
- `CLAUDE.md` und `AGENTS.md` — `AGORA_ALLOW_ANONYMOUS` dokumentiert.
- ggf. `.env.example` (falls vorhanden) ergänzen.

## Verifikationsplan

- `cd backend && uv run pytest tests/test_config_validate.py`
- `cd backend && uv run pytest` Full-Suite grün
- `npm run check`

## Status

**Erledigt 2026-04-29.**

## Ergebnis

- `Config.validate()` lehnt Startup ab, wenn `FLASK_DEBUG=false`, `AGORA_AUTH_TOKEN` leer und `AGORA_ALLOW_ANONYMOUS` nicht truthy.
- Truthy-Werte für Allow-Flag: `true`, `1`, `yes` (case-insensitive). Konsistent mit dem Pattern für `ENABLE_AGENT_TOOLS`.
- Doku in `CLAUDE.md`, `AGENTS.md`, `.env.example` synchron.
- Neue Test-Datei `backend/tests/test_config_validate.py` mit 5 Cases (Debug erlaubt fehlenden Token / Non-Debug ohne Token failt / Token reicht / Allow-Flag reicht / Allow-Flag toleriert verschiedene Truthy-Schreibweisen).

## Verifikation

- `uv run pytest tests/test_config_validate.py` → 5/5 grün.
- `uv run pytest` (Full-Suite) → 298 passed, 2 skipped (Redis-Integration nur via `TEST_REDIS_URL`).
- `uv run ruff check app/config.py tests/test_config_validate.py` → clean.

## Folgewirkung

- Bestehende Deployments mit `FLASK_DEBUG=false` und ohne Token brechen jetzt **bewusst** beim Start. Migrationspfad: `AGORA_AUTH_TOKEN` setzen oder `AGORA_ALLOW_ANONYMOUS=true` opt-out.
- Bekannt: `log_auth_mode` in `utils/auth.py` unterscheidet noch nicht zwischen „kein Token & Allow-Flag" und „kein Token & Debug" — wird in P0.1b geschärft.
