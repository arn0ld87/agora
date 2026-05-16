# P1.1 Pflichtabschnitt-Validator Arbeitsprotokoll

## Kontext

PLAN.md §2.1 verlangt, dass Report-Outlines die 11 Default-Pflichtabschnitte aus `report_prompts.DEFAULT_REPORT_SECTIONS` vollständig enthalten. Unvollständige Outlines dürfen nicht als fertige Reports finalisiert werden.

## Änderungen

1. `backend/app/services/report_agent/contract_validator.py` ergänzt `validate_required_sections()` als kleinen, case-insitiven und whitespace-toleranten Validator.
2. `ReportOutlineModel` validiert lazy gegen `DEFAULT_REPORT_SECTIONS`; `ReportStatus` kennt `incomplete`, `ReportModel` liefert `missing_sections[]` strukturiert aus.
3. Der Dataclass-Mirror `Report` persistiert `missing_sections[]`; `ReportManager.save_report()` schreibt für `incomplete` keine Markdown-Datei.
4. `workflow.generate_report()` blockt nach der Outline-Planung mit `ReportStatus.INCOMPLETE`, speichert die fehlenden Titel und bricht vor Section-Generierung/Markdown-Finalisierung ab.
5. `GET /api/report/<id>` liefert `status` und `missing_sections[]` über den bestehenden Contract-Pfad aus; bei `incomplete` bleibt `outline` bewusst `null`, weil unvollständige Outlines vertragswidrig sind.

## Korrektur: ReportStatus-Duplikat

`report_contract.py::ReportStatus` enthielt nach dem Sub-Slice sowohl `incomplete = "incomplete"` als auch `INCOMPLETE = "incomplete"`. Pydantic v2 generiert beide Alias-Varianten ins JSON-Schema, was `"incomplete"` doppelt in der `enum`-Liste erzeugte. Behoben: Canonical-Member ist `INCOMPLETE = "incomplete"` (konsistent mit `models/report.py`), `incomplete`-Alias entfernt. Alle bestehenden Caller verwenden `ReportStatus.INCOMPLETE`.

## Schema-Drift (erwartet)

`dump_schemas` fügt zu `report-contract.schema.json` und `report.schema.json` hinzu:
- `missing_sections` (Array of string) in `ReportModel`-Properties
- `"incomplete"` zum Status-Enum (einmalig, ohne Duplikat)

## Tests

- Contract-Test `test_outline_rejects_missing_required_sections` — PASS
- Unit-Tests `test_validate_required_sections_case_insensitive` — PASS
- Workflow-Test `test_generate_report_blocks_incomplete_outline_before_markdown_finalize` — PASS
- Bestehende Outline-/Strict-Schema-Tests wurden auf vollständige Default-Sections angepasst, wo sie den Contract-Pfad validieren.
- Volltest: 1711 passed, 9 skipped — keine Regression.
