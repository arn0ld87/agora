### Geändert

- **Frontend (`reportViewState`)**: Statusmengen (`pending`/`planning`/`generating` vs. `completed`/`incomplete`/`failed`), `RunRegistry`-Gegenprüfung (`pending`/`processing`), HTTP-404/`not_found`- vs. 409-`report_generate_in_progress`-Klassifikation sowie `ReportState`-/ `EvidenceState`-Ableitung in `frontend/src/composables/run/report/reportViewState.ts` konsolidiert; `useRunReport`, `useReportGeneration`, `reportSections`, `useReportArtifacts`, `ReportReadingPane` und `ReportEvidencePanel` delegieren an das gemeinsame Modul.
