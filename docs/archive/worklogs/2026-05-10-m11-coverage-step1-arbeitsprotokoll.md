# Arbeitsprotokoll: M11.2/M11.3 Coverage-Schwellen-Step1

**Datum:** 2026-05-10
**Branch:** `feat/m11-coverage-step1`
**Sub-Slice:** M11.2/M11.3 Step1 (vorgezogen, war 2026-06-04 geplant)

## Vorher / Nachher

| Komponente | Schwelle vorher | Schwelle nachher | Ist-Wert (2026-05-10) |
|---|---|---|---|
| Backend (`--cov-fail-under`) | 53 % | 55 % | 61.41 % |
| Frontend statements | 24 % | 26 % | 50.46 % |
| Frontend branches | 24 % | 26 % | 39.56 % |
| Frontend functions | 24 % | 26 % | 38.59 % |
| Frontend lines | 24 % | 26 % | 52.50 % |

## Lokale Verifikation

### Backend

```
uv run pytest --cov=app --cov-report=term --cov-fail-under=55 -q -m "not llm"
```

Ergebnis:
- 1692 passed, 9 skipped, 7 deselected, 3 warnings
- Total coverage: 61.41 %
- "Required test coverage of 55% reached." — GRUEN

Die 9 Skips:
- 1x `test_event_bus_redis` (kein Redis, erwartet)
- 1x `test_subprocess_redis_bridge` (kein Redis, erwartet)
- 7x `test_compose_snapshot` (kein `.env` mit NEO4J_PASSWORD, erwartet)

### Frontend

```
npm run test:coverage
```

Ergebnis (45 spec files, 465 tests passed):

| Metrik | Ist | Schwelle | Status |
|---|---|---|---|
| Statements | 50.46 % (2536/5025) | 26 % | GRUEN |
| Branches | 39.56 % (1368/3458) | 26 % | GRUEN |
| Functions | 38.59 % (455/1179) | 26 % | GRUEN |
| Lines | 52.50 % (2380/4533) | 26 % | GRUEN |

### Lint + Types

```
uv run ruff check app/ tests/  -> All checks passed!
uv run mypy app                -> Success: no issues found in 132 source files
```

### Schemas idempotent

```
uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/  -> (kein Diff)
```

### status.md sync-check

```
bash scripts/sync-status.sh --check -> OK: docs/status.md in sync
```

## Geaenderte Dateien

| Datei | Aenderung |
|---|---|
| `.github/workflows/ci.yml` | `--cov-fail-under=53` → `--cov-fail-under=55`, Kommentar aktualisiert |
| `frontend/vite.config.js` | alle vier `thresholds`-Metriken 24 → 26, Kommentar aktualisiert |
| `docs/status.md` | Backend-Schwelle, Backend-Roadmap-Tabelle, Frontend-Schwelle, Frontend-Roadmap-Tabelle, Milestone-Erledigt-Zeilen, Mittelfristig-Zeile |
| `CHANGELOG.md` | Bullet unter `[Unreleased] ### Changed` |
| `docs/2026-05-10-m11-coverage-step1-arbeitsprotokoll.md` | dieses Protokoll |

## Begründung der Vorziehung

Ist-Werte aus CI-Run nach Followup-5 (stabil grün):
- Backend 61.41 % liegt 6.41 Punkte über der neuen Schwelle 55 %
- Frontend alle vier Metriken mind. 12 Punkte über der neuen Schwelle 26 %

Die ursprüngliche Roadmap sah die Anhebung für 2026-06-04 vor. Da der CI
seit Followup-5 (M11.4b-Followup-5, event-bus-tmp-race-fix) stabil grün
ist und die Ist-Werte deutlich decken, wurde der Schritt auf 2026-05-10
vorgezogen.

## Naechste Anhebung (Roadmap)

| Datum | Backend | Frontend |
|---|---|---|
| 2026-06-10 | 57 % | 28 % |
| 2026-07-10 | 59 % | 30 % |
| … (monatlich) | +2 % | +2 % |
| Langfristziel | 85 % | 80 % |
