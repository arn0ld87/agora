# Arbeitsprotokoll: M11.2/M11.3 Coverage-Schwellen-Step 2

**Datum:** 2026-06-10 (vorgezogen am 2026-05-11 für CI-Cleanup)
**Branch:** `feat/m11-coverage-step2`
**Sub-Slice:** M11.2/M11.3 Step 2

## Vorher / Nachher

| Komponente | Schwelle vorher | Schwelle nachher | Ist-Wert (2026-05-11) |
|---|---|---|---|
| Backend (`--cov-fail-under`) | 55 % | 60 % | 65.99 % |
| Frontend statements | 26 % | 28 % | 53.45 % |
| Frontend branches | 26 % | 28 % | 41.84 % |
| Frontend functions | 26 % | 28 % | 42.41 % |
| Frontend lines | 26 % | 28 % | 55.63 % |

## Lokale Verifikation

### Backend

```
cd backend && uv run pytest --cov=app --cov-report=term --cov-fail-under=60
```

Ergebnis:
- 1965 passed, 9 skipped, 7 deselected
- Total coverage: 65.99 %
- "Required test coverage of 60% reached." — GRUEN

Die Steigerung von 61.41 % auf 65.99 % wurde durch neue Unit-Tests für `app/utils/file_parser.py` erreicht (Coverage der Datei von 12 % auf 31 % gesteigert).

### Frontend

```
cd frontend && npm run test:coverage
```

Ergebnis (49 spec files):

| Metrik | Ist | Schwelle | Status |
|---|---|---|---|
| Statements | 53.45 % | 28 % | GRUEN |
| Branches | 41.84 % | 28 % | GRUEN |
| Functions | 42.41 % | 28 % | GRUEN |
| Lines | 55.63 % | 28 % | GRUEN |

## Geaenderte Dateien

| Datei | Aenderung |
|---|---|
| `backend/tests/utils/test_file_parser.py` | Neue Tests für `file_parser.py` |
| `.github/workflows/ci.yml` | `--cov-fail-under=55` → `--cov-fail-under=60`, Kommentar aktualisiert |
| `frontend/vite.config.js` | alle vier `thresholds`-Metriken 26 → 28, Kommentar aktualisiert |
| `docu/STATUS.md` | Schwellen und Roadmap aktualisiert |
| `CHANGELOG.md` | [Unreleased] Block ergänzt |
| `docu/2026-06-10-m11-coverage-step2-arbeitsprotokoll.md` | dieses Protokoll |

## Begründung

Die Anhebung auf Step 2 (geplant für 2026-06-10) wurde vorgezogen, da durch die Ergänzung von Tests für den kritischen Pfad der Dokumenten-Extraktion (`file_parser.py`) die Backend-Coverage signifikant gesteigert werden konnte. Die Ist-Werte liegen nun für beide Komponenten deutlich über den neuen Schwellen (Backend +5.99 Punkte Puffer, Frontend mind. +13 Punkte Puffer).

## Naechste Anhebung (Roadmap)

| Datum | Backend | Frontend |
|---|---|---|
| 2026-07-10 | 62 % | 30 % |
| 2026-08-10 | 64 % | 32 % |
| … (monatlich) | +2 % | +2 % |
| Langfristziel | 85 % | 80 % |
