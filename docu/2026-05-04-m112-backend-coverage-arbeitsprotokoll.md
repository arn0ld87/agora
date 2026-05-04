# Arbeitsprotokoll — M11.2: Backend-Coverage-Gate

**Datum:** 2026-05-04
**Slice-ID:** M11.2 / PLAN.md F6.1
**Ziel:** `pytest-cov` als Dev-Dependency, Coverage-Gate in CI, Startschwelle ermitteln und dokumentieren.

## Initial-Coverage-Messung

Gemessen vor allen Edits mit temporär installiertem `pytest-cov`:

```bash
cd backend && uv run pytest --cov=app --cov-report=term -q
```

Ergebnis (1425 passed, 9 skipped, Marker `-m 'not llm'` aktiv):

| Scope | Statements | Missed | Coverage |
|---|---|---|---|
| `app/` gesamt | 12 842 | 5 733 | **55 %** |
| `app/services/` | 6 964 | 3 427 | **51 %** |

## Begründung der gewählten Schwelle

Ist-Wert 55 % liegt unter der PLAN-Default-Schwelle von 70 %. Daher greift die Fallback-Formel:

> Ist < 70 % → `--cov-fail-under=floor(Ist - 2)` = `floor(55 - 2)` = **53**

Die 70 %-Marke ist vorerst nicht erreichbar, weil zwei besonders schwere Dateien ausschließlich über Subprozess-Tests mit laufender Ollama-Instanz und Neo4j-Instanz abdeckbar sind und daher in CI übersprungen werden (`-m 'not llm'`):

- `app/services/simulation_runner.py`: 809 Statements, 22 % Coverage
- `app/services/graph_tools.py`: 667 Statements, 19 % Coverage

Diese Lücke ist strukturell, nicht durch neue Unit-Tests zu schließen, ohne die OASIS-Integrationsschicht zu mocken (eigener Slice, Out-of-Scope hier).

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `backend/pyproject.toml` | `pytest-cov>=5.0.0` in `[project.optional-dependencies] dev` und `[dependency-groups] dev`; `addopts` um Coverage-Flags erweitert |
| `.github/workflows/ci.yml` | `Upload coverage report`-Step nach `Run backend tests` (Artifact `backend-coverage`, 14 Tage, `if-no-files-found: error`) |
| `docu/STATUS.md` | Neue Sektion `Backend-Coverage (M11.2)` mit Messwerten, Schwellenbegründung und Roadmap-Tabelle; Aktualisierungsprotokoll-Eintrag |
| `CHANGELOG.md` | Eintrag unter `[Unreleased] ### Added` |
| `docu/2026-05-04-m112-backend-coverage-arbeitsprotokoll.md` | dieses Dokument |

## Verify-Output

```
# 1. uv sync --group dev
uv sync --group dev  → pytest-cov==7.1.0 aufgelöst, kein Konflikt

# 2. Schemas-Drift-Check
uv run python -m app.contracts.dump_schemas && git diff --exit-code schemas/
→ Exit 0, kein Drift

# 3. Volltest mit Coverage-Gate (--cov-fail-under=53)
uv run pytest -q
→ 1425 passed, 9 skipped, 4 deselected, 3 warnings
→ TOTAL 55 % >= 53 % → Gate grün

# 4. Ruff
uv run ruff check app/ tests/
→ Exit 0, keine Findings
```

Alle vier Checks grün.
