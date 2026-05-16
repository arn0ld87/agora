# Worklog — pydantic-settings Foundation (ADR-0003 PR 1)

**Datum:** 2026-05-15
**Worktree:** `/private/tmp/agora-pydantic-settings-pr1`
**Branch:** `feat/pydantic-settings-foundation`
**Worker:** Agora-Backend-Refactor-Worker (Claude Sonnet 4.6)

## Was wurde gebaut

`backend/app/settings.py` — `AgoraSettings(BaseSettings)` mit 41 Feldern und 12 Validatoren, die alle Settings aus `app/config.py` 1:1 spiegeln. `get_settings()` via `lru_cache(maxsize=1)`, `reload_settings()` als Convenience-Helper, `bootstrap_settings_if_missing_secret_in_debug()` als App-Start-Werkzeug für PR 2.

`backend/tests/test_settings.py` — 56 Unit-Tests in 5 Klassen: Defaults (15), EnvOverride (9), Validators (32 Fälle), Cache (4), SecretStr (4).

`backend/pyproject.toml` — `pydantic-settings>=2.5.0` eingefügt.

**Bewusst nicht angefasst:** `app/config.py`, `conftest.py`, alle Call-Sites, Frontend, scripts/.

## Auffälligkeit: pydantic-settings 2.x JSON-Pre-Parse

pydantic-settings 2.12 (installiert) versucht für `dict`-annotierte Felder einen eigenen `json.loads()` **vor** dem `field_validator(mode="before")`. Bei ungültigem JSON-String wirft es `SettingsError` bevor der Fail-Soft-Validator greifen kann.

Lösung: `llm_model_context_limits` als `Any` annotiert. Der `field_validator` normalisiert zur Laufzeit auf `dict[str, int]` und gibt `{}` bei ungültigem JSON zurück. Das Verhalten ist identisch zu `Config.LLM_MODEL_CONTEXT_LIMITS` (try/except → `{}`).

## Validator-Coverage

12/12 Validatoren implementiert und durch Tests abgedeckt:

1. `_normalize_report_toolcall_mode` — Fail-Soft zu `"xml"`, getestet mit `"native"`, `"XML"`, `"Garbage"`
2. `_normalize_ontology_mutation_mode` — Literal-Whitelist, getestet mit `"REVIEW_ONLY"` (pass) und `"invalid"` (ValidationError)
3. `_normalize_event_bus_backend` — Literal-Whitelist, getestet mit `"REDIS"` (pass) und `"kafka"` (ValidationError)
4. `_normalize_agora_log_format` — Literal-Whitelist, getestet mit `"JSON"` (pass) und `"yaml"` (ValidationError)
5. `_normalize_agent_language` — Strip+lower, getestet mit `"EN"` → `"en"`
6. `_parse_llm_model_context_limits_json` — JSON-Parse + Fail-Soft `{}`, getestet mit valid JSON und `"NOT_JSON"`
7. `_embedding_api_key_fallback_to_llm` — Fallback auf `llm_api_key`, getestet
8. `_validate_vector_dim_matches_model` — Mismatch → ValidationError, unknown model → kein Check
9. `_validate_secrets_in_prod` — leer + Placeholder → ValidationError, debug → skip
10. `_validate_neo4j_password_in_prod` — Placeholder → ValidationError, debug → skip
11. `_validate_auth_in_prod` — kein Token + kein Anon → ValidationError, `allow_anonymous=true` → pass
12. `_validate_llm_api_key_present` — leer/None → ValidationError

## Test-Count-Delta

- Baseline (main): 2144 passed, 7 skipped
- Nach PR 1: 2200 passed, 7 skipped (+56 neue Tests, 0 Regressions)

## Verifikations-Output

```
ruff check app/ tests/   → All checks passed!
mypy app                 → Success: no issues found in 167 source files
pytest tests/test_settings.py  → 56 passed in 0.32s
pytest (volle Suite)     → 2200 passed, 7 skipped in 14.12s
```
