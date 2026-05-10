# Arbeitsprotokoll: Sub-Slice P3.1 — ReportV3 als Persistenz-Format

**Datum:** 2026-05-10
**Refs:** PLAN.md §4.1, Worktree `p3-1-report-v3-persistenz`

## Ausgangslage

- `ReportV3`-Modell in `backend/app/contracts/report_v3.py` bereits vollständig (11 DTOs + Container).
- `storage.py` hatte Pfad-Helper `get_report_v3_path` + `get_report_v3_markdown_path`, aber keinen Writer/Reader.
- `manager.py` hatte `build_report_v3` + `save_report_v3` und rief diese bei `save_report()` bereits auf.
- `evidence_migrations.py` hatte `migrate_v1_to_v2`, aber kein `migrate_v2_to_v3`.
- Import-Smoke `migrate_v2_to_v3` / `write_report_v3` / `read_report_v3` schlug fehl.

## Durchgeführte Änderungen

### 1. `backend/app/services/evidence_migrations.py`

- `migrate_v2_to_v3(raw, *, simulation_id=None) -> dict` ergänzt.
- Leitet Claims (mit Evidence-Refs) und DataGaps (inkl. Hypothesen) aus der v2-Sections-Struktur ab.
- Emittiert Personas/Segments/FrictionPoints/TrustSignals als leere Listen (v2 enthält diese nicht).
- Fügt bei fehlenden Personas einen `DataGap`-Hinweis mit `id="dg-migration-personas"` ein.
- `CURRENT_SCHEMA_VERSION = 2` bleibt unverändert (ist Evidence-Map-Version, nicht Report-Container-Version).
- Docstring aktualisiert.

### 2. `backend/app/services/report_agent/storage.py`

- `write_report_v3(report_id, report_v3, *, reports_dir=None) -> str` ergänzt.
  - Atomar via `.tmp` + `os.replace`.
  - Schreibt `report_v3.model_dump_json(indent=2, by_alias=False)`.
  - Liefert absoluten Pfad.
- `read_report_v3(report_id, *, reports_dir=None) -> ReportV3 | None` ergänzt.
  - Liest + validiert via `ReportV3.model_validate()`; gibt `None` bei Fehler/Fehlen.
- `__all__` um `read_report_v3` und `write_report_v3` erweitert.
- `TYPE_CHECKING`-Guard für `ReportV3`-Import (zirkuläre Import-Vermeidung).

### 3. `backend/tests/contracts/test_report_v3_contract.py`

6 neue Tests:
- `test_migrate_v2_to_v3_minimal` — Claims + DataGaps korrekt extrahiert.
- `test_migrate_v2_to_v3_empty_sections_produces_valid_v3` — leere Sections → valides v3.
- `test_migrate_v2_to_v3_simulation_id_in_hint` — simulation_id im DataGap-Hinweis sichtbar.
- `test_migrate_v2_to_v3_skips_claims_without_evidence` — Claims ohne evidence werden übersprungen.
- `test_write_and_read_report_v3_roundtrip` — atomic write + read via tmp_path.
- `test_read_report_v3_returns_none_when_missing` — defensives Lesen bei fehlendem File.

## Akzeptanz-Ergebnis

```
# 1. Import-Smoke
OK

# 2. Schema-Dump
12 Schemas regeneriert — git diff schemas/ leer (kein Drift, report_v3.py unverändert)

# 3. Contract-Tests
24 passed in 4.21s

# 4. Volltest
1774 passed, 9 skipped in 132.17s
```

## Invarianten eingehalten

- `CURRENT_SCHEMA_VERSION = 2` nicht angehoben.
- v2-Storage (`meta.json`, `full_report.md`) unverändert.
- `manager.py` unverändert — `save_report_v3(build_report_v3(...))` war bereits verdrahtet.
- Keine `print()`-Statements; strukturiertes Logging via `logging.getLogger`.
- Kein neuer `dataclass`-Import.
- Keine Inline-JSON-Schemas.
