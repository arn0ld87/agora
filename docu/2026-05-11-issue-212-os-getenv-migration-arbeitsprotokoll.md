# Issue #212 — os.getenv-Migration via settings_layer (2026-05-11)

## Was

Letzter offener Akzeptanz-Punkt von Issue #212 (Live-Settings):
`os.getenv`/`os.environ.get` in Service-Files durch `settings_layer`-Lookups ersetzen,
damit Live-Settings-Änderungen via `PUT /api/settings` ohne Restart wirken.

## Geänderte Files

| File | Änderung |
|------|----------|
| `backend/app/services/settings_schema.py` | 3 neue FieldSpecs: `ONTOLOGY_MAX_TOKENS` (ontology, int, default 12288), `AGORA_PARALLEL_PERSONA_COUNT` (oasis, int, default 10), `AGORA_PERSONA_DETAIL_LEVEL` (oasis, enum compact/standard/rich, default standard) |
| `backend/app/services/prepare_service.py` | `os.environ.get('AGORA_PARALLEL_PERSONA_COUNT', '10')` → `_get_settings().effective_value(...)` |
| `backend/app/services/oasis_profile_generator.py` | 2 Stellen: `_resolve_persona_detail_level()` + parallele Zählung |
| `backend/app/services/ontology_generator.py` | `os.environ.get('ONTOLOGY_MAX_TOKENS', '12288')` → `_get_settings().effective_value(...)` |
| `backend/app/services/sim/process_manager.py` | Inline-Kommentar `# env-only: ...` an 3 bewusst beibehaltenen Stellen |
| `backend/tests/test_settings_layer.py` | 12 neue Tests (Pin-Tests + Env-Override + Live-PUT je Key) |
| `CHANGELOG.md` | `[Unreleased]`-Eintrag |

## Neu registrierte Settings-Layer-Keys

- `ONTOLOGY_MAX_TOKENS` — int, Section ontology, Default 12288, min 1024, max 131072
- `AGORA_PARALLEL_PERSONA_COUNT` — int, Section oasis, Default 10, min 1, max 50
- `AGORA_PERSONA_DETAIL_LEVEL` — enum, Section oasis, Default standard, Werte: compact/standard/rich

## Warum env-only-Stellen in process_manager.py belassen

- `os.environ.copy()` (Zeile 268): Vererbt das vollständige Prozess-Environment an den OASIS-Subprozess. Ein settings_layer-Lookup wäre hier semantisch falsch — der Subprozess braucht alle Env-Vars (PATH, PYTHONPATH, etc.), nicht nur die Settings-Felder.
- `WERKZEUG_RUN_MAIN` / `FLASK_DEBUG` (Zeile 519–522): Flask/Werkzeug-Reloader-Interna, die der Werkzeug-Prozessmanager selbst schreibt. Kein Anwendungs-Setting.

## Tests

136 Settings-Tests (layer + api + persistence + validator) alle grün.
Gesamter Test-Run: 1826 passed, 9 skipped (Redis/Docker — erwartete Infra-Skips).

## Risiken

Kein. Die Migration ist rein lesend auf den Settings-Layer-Singleton. Defaults im Schema sind identisch zu den vorherigen `os.environ.get`-Fallbacks. Der Settings-Layer liest `os.environ` weiterhin als Layer-3-Quelle, d.h. bestehende `.env`-Konfigurationen wirken unverändert. Zusätzlich ist jetzt ein in-memory Override (PUT /api/settings) ohne Restart wirksam.
