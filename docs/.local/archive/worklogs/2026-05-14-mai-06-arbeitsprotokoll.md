# Arbeitsprotokoll — MAI-06: ReportV3 als Single Source of Truth

**Datum:** 2026-05-14  
**Branch:** `feat/mai-06-retire-v2-md`  
**Scope:** Backend only — 4 Files geändert, 1 Script neu.

## Aufgabe

`full_report.md` wird nicht mehr stumm als zweite Persistenz-Kopie geschrieben.  
ReportV3 (`report-v3.json`) ist die einzige strukturierte Quelle.  
Markdown-Export rendert on-demand via `render_report_v3()`.

## Risk-Einschätzung (Opus-Pre-Review)

- Impact Radius: HIGH — 76 Files direkt, 500+ Nodes im 2-Hop-Radius
- Änderungen sind chirurgisch auf 3 Backend-Files + 1 Test-File + 1 Script begrenzt
- Bestandsreports werden NICHT gelöscht (Read-Pfad `get_report` bleibt)

## Voraussetzungen

MAI-02 (DataGap-Slot) und MAI-03 (Hypothesen-Slot) sind durch.  
ReportV3 hat alle Felder für vollständigen on-demand-Render.

## Änderungen

### `backend/app/services/report_agent/manager.py`

1. **`assemble_full_report()`**: Entfernt den `with open(..., 'w') as f: f.write(md_content)`-Block.  
   Gibt nur noch den Markdown-String zurück (in-memory only).  
   Logger-Message: `"Markdown-String assembliert (in-memory only): {report_id}"`.

2. **`save_report()`**: Entfernt den `if report.status != ReportStatus.INCOMPLETE and report.markdown_content:` Block, der `full_report.md` schrieb.  
   Der `save_report_v3`-Aufruf bei COMPLETED-Reports mit Evidence bleibt.  
   Logger-Message: `"report saved (v3-only): {report_id}"`.

3. **Neu: `build_report_v3_markdown(report_id)`**: Class-Method.  
   Lädt `report-v3.json` via `get_report_v3()`, validiert als `ReportV3`, rendert via `render_report_v3()`.  
   Gibt `None` zurück wenn kein v3-Artefakt vorhanden (→ Export-Fallback auf `markdown_content`).

### `backend/app/api/report.py`

**`export_report()`** — `fmt == 'md'`-Branch:  
Ersetzt `send_file(md_path)` durch `ReportManager.build_report_v3_markdown(report_id)`.  
Fallback: `report.markdown_content or ""` für Bestandsreports ohne v3-Artefakt.  
`send_file` und `os.path.exists`-Checks für `report-v3.md` / `full_report.md` entfernt.

### `backend/tests/test_report_export.py`

- **`_persist_report(with_evidence=True)`**: Reihenfolge korrigiert — Evidence-Map wird jetzt
  **vor** `save_report()` gespeichert, damit `save_report` → `save_report_v3` das v3-Artefakt
  bei COMPLETED-Reports schreiben kann (war vorher umgekehrt, v3 wurde nie geschrieben).

- **`test_export_md_prefers_report_v3_markdown`**: Neu: Verifiziert dass der Export
  on-demand aus `report-v3.json` rendert (`"# Agora ReportV3"`, `"**Report-Modus:**"`).
  Ersetzt den alten Test der eine manuell geschriebene `.md`-Datei prüfte
  (war Pre-MAI-06-Verhalten: `send_file(report-v3.md)`).

### `backend/scripts/migrate_v2_full_report_to_v3.py` (neu)

Inventar-Skript (nicht destruktiv).  
Scannt `backend/uploads/reports/`, ermittelt welche Reports v2-md und/oder v3-json haben.  
Schreibt Audit nach `docu/2026-05-14-mai-06-bestandsinventar.md`.

## Verifikation

```
rg -n 'open.*_get_report_markdown_path\|write.*full_report' backend/app/services/report_agent/manager.py
# → 0 Matches (kein Write-Call mehr)

cd backend && uv run pytest tests/test_report_export.py tests/contracts/ -x -q
# → 159 passed

uv run ruff check . && uv run mypy app --ignore-missing-imports
# → All checks passed / Success: no issues found in 155 source files

uv run python backend/scripts/migrate_v2_full_report_to_v3.py
# → OK: Inventur unter docu/2026-05-14-mai-06-bestandsinventar.md
```

## Volltest-Delta (vor/nach)

Vor: 4 pre-existierende Failures (`test_report_modes`, `test_simulation_uses_request_model`),  
unabhängig von MAI-06 (LLM_API_KEY / Neo4j-Umgebung fehlt im Test-Runner).  
Nach: identisch — keine neuen Failures eingeführt.

## Nicht geändert (Scope-Compliance)

- Keine anderen API-Routes
- Keine Contracts (`app/contracts/`)
- Kein Frontend
- Kein Push, kein PR (obliegt dem Lead)
